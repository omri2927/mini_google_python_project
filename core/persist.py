import gzip
import json
import os
from pathlib import Path
from copy import deepcopy

from core.models import FileRecord, Hit, FileType

SUPPORTED_INDEX_FORMAT_VERSIONS = {"1"}

# ------------------------------------------------------------
# Save index and metadata to disk
# ------------------------------------------------------------
def save_index(
        *,
        files: list[FileRecord],
        index: dict[str, list[Hit]],
        out_dir: str,
        meta: dict
) -> None:
    """
    Save the search index to disk.

    Files written:
    - meta.json        -> metadata + file list
    - index.jsonl.gz   -> inverted index (token per line)

    Raises:
        RuntimeError on failure
    """
    if not Path(out_dir).is_dir():
        raise NotADirectoryError(f"{out_dir} is not a directory")

    meta_json = deepcopy(meta)

    meta_filename = os.path.join(out_dir, "meta.json")
    index_filename = os.path.join(out_dir, "index.jsonl.gz")

    # Store file metadata
    meta_json["files"] = [
        {
            "path": f.path,
            "size": f.size,
            "mtime": f.mtime,
            "filetype": getattr(f.filetype, "name", str(f.filetype)),
        }
        for f in files
    ]

    try:
        # Write metadata
        with open(meta_filename, "w", encoding="utf-8") as meta_file:
            json.dump(meta_json, meta_file, indent=4, ensure_ascii=False)

        # Write inverted index (JSON Lines, gzip-compressed)
        with gzip.open(index_filename, "wt", encoding="utf-8") as index_file:
            for token, hits in index.items():
                token_entry = {
                    "token": token,
                    "hits": {}
                }

                for hit in hits:
                    file_id = str(hit.file_id)
                    token_entry["hits"].setdefault(file_id, []).append(hit.line_no)

                index_file.write(json.dumps(token_entry, ensure_ascii=False) + "\n")

    except Exception as e:
        raise RuntimeError(
            f"An error occurred while saving meta and index data: {e}"
        ) from e


# ------------------------------------------------------------
# Load index and metadata from disk
# ------------------------------------------------------------
def load_index(
        in_dir: str
) -> tuple[list[FileRecord], dict[str, list[Hit]], dict]:
    meta_filename = os.path.join(in_dir, "meta.json")
    index_filename = os.path.join(in_dir, "index.jsonl.gz")

    if not Path(meta_filename).is_file() or not Path(index_filename).is_file():
        raise FileNotFoundError(f"meta.json or index.jsonl.gz not found in {in_dir}")

    meta_dict: dict = {}
    all_file_records: list[FileRecord] = []
    index_dict: dict[str, list[Hit]] = {}

    try:
        with open(meta_filename, "r", encoding="utf-8") as meta_file:
            meta_dict = json.load(meta_file)

            if "index_format_version" not in meta_dict.keys():
                raise RuntimeError("Meta missing index_format_version")

            if meta_dict["index_format_version"] not in SUPPORTED_INDEX_FORMAT_VERSIONS:
                raise RuntimeError(f"Unsupported index format version: {meta_dict['index_format_version']}. \
                 Supported: {SUPPORTED_INDEX_FORMAT_VERSIONS}")

        for f in meta_dict["files"]:
            try:
                filetype = FileType[f["filetype"]]
            except KeyError:
                raise ValueError(f"Unknown file type in index: {f['filetype']}")
            all_file_records.append(
                FileRecord(f["path"], f["size"], f["mtime"], filetype)
            )

        # Optional validation
        is_valid, problems = validate_index(files=all_file_records)
        meta_dict["validation"] = {"is_valid": is_valid, "problems": problems}

        with gzip.open(index_filename, mode="rt", encoding="utf-8") as index_file:
            for line in index_file:
                data = json.loads(line)
                token = data["token"]

                index_dict[token] = []
                for file_id, line_numbers in data["hits"].items():
                    file_id = int(file_id)
                    for line_no in line_numbers:
                        index_dict[token].append(Hit(file_id, line_no, -1, -1))

    except json.JSONDecodeError:
        raise RuntimeError("Index file is corrupted or malformed JSON.")
    except Exception as e:
        raise RuntimeError(f"An error occurred while loading index data: {e}") from e

    return all_file_records, index_dict, meta_dict


# ------------------------------------------------------------
# Validate that indexed files still exist and match metadata
# ------------------------------------------------------------
def validate_index(
        *,
        files: list[FileRecord]
) -> tuple[bool, list[str]]:
    problems: list[str] = []

    for file_record in files:
        path = file_record.path

        if not Path(path).is_file():
            problems.append(f"Missing file: {path}")
            continue

        if os.path.getsize(path) != file_record.size:
            problems.append(f"File size changed: {path}")

        if os.path.getmtime(path) != file_record.mtime:
            problems.append(f"File modified time changed: {path}")

    return len(problems) == 0, problems
