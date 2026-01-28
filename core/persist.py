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
    files_by_id: dict[int, FileRecord],
    id_by_path: dict[str, int],
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

    meta_json["id_by_path"] = id_by_path

    # Store file metadata
    meta_json["files"] = [
        {
            "id": f_id,
            "path": f.path,
            "size": f.size,
            "mtime": f.mtime,
            "filetype": getattr(f.filetype, "name", str(f.filetype)),
        }
        for f_id, f in files_by_id.items()
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
                    token_entry["hits"].setdefault(file_id, []).append([hit.unit_index, hit.count])

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
) -> tuple[dict[int, FileRecord],
           dict[str, int],
           dict[str, list[Hit]],
           dict]:
    meta_filename = os.path.join(in_dir, "meta.json")
    index_filename = os.path.join(in_dir, "index.jsonl.gz")

    if not Path(meta_filename).is_file() or not Path(index_filename).is_file():
        raise FileNotFoundError(f"meta.json or index.jsonl.gz not found in {in_dir}")

    meta_dict: dict = {}
    all_file_records: dict[int, FileRecord] = dict()
    id_by_path: dict[str, int] = dict()
    index_dict: dict[str, list[Hit]] = {}

    try:
        with open(meta_filename, "r", encoding="utf-8") as meta_file:
            meta_dict = json.load(meta_file)

            if "index_format_version" not in meta_dict:
                raise RuntimeError("Meta missing index_format_version")

            if meta_dict["index_format_version"] not in SUPPORTED_INDEX_FORMAT_VERSIONS:
                raise RuntimeError(f"Unsupported index format version: {meta_dict['index_format_version']}. \
                 Supported: {SUPPORTED_INDEX_FORMAT_VERSIONS}")

        for f in meta_dict["files"]:
            try:
                filetype = FileType[f["filetype"]]
            except KeyError:
                raise ValueError(f"Unknown file type in index: {f['filetype']}")
            all_file_records[f["id"]] = FileRecord(path=f["path"], size=f["size"], mtime=f["mtime"], filetype=filetype)

        id_by_path = meta_dict.get("id_by_path", {})

        # Optional validation
        is_valid, problems = validate_index(files_by_id=all_file_records)
        meta_dict["validation"] = {"is_valid": is_valid, "problems": problems}

        with gzip.open(index_filename, mode="rt", encoding="utf-8") as index_file:
            for line in index_file:
                data = json.loads(line)
                token = data["token"]

                index_dict[token] = []
                for file_id_str, hits_list in data.get("hits", {}).items():
                    fid = int(file_id_str)
                    index_dict[token].extend([Hit(fid, h[0], h[1]) for h in hits_list])


    except json.JSONDecodeError:
        raise RuntimeError("Index file is corrupted or malformed JSON.")
    except Exception as e:
        raise RuntimeError(f"An error occurred while loading index data: {e}") from e

    return all_file_records, id_by_path, index_dict, meta_dict


# ------------------------------------------------------------
# Validate that indexed files still exist and match metadata
# ------------------------------------------------------------
def validate_index(
        *,
        files_by_id: dict[int, FileRecord]
) -> tuple[bool, list[str]]:
    """
    Checks if indexed files still match their disk state.
    Returns (is_valid, list_of_problems).
    """
    problems: list[str] = []

    # Tolerance for mtime (e.g., 2 seconds for FAT32 or network drives)
    MTIME_TOLERANCE = 2.0

    for fid, record in files_by_id.items():
        p = Path(record.path)

        try:
            if not p.is_file():
                problems.append(f"[{fid}] Missing file: {record.path}")
                continue

            # Get size and mtime in one go for efficiency
            stats = p.stat()

            # Check Size
            if stats.st_size != record.size:
                problems.append(f"[{fid}] Size changed: {record.path} (Index: {record.size}, Disk: {stats.st_size})")

            # Check Modified Time with tolerance
            if abs(stats.st_mtime - record.mtime) > MTIME_TOLERANCE:
                problems.append(f"[{fid}] Content changed (mtime): {record.path}")

        except PermissionError:
            problems.append(f"[{fid}] Permission denied: {record.path}")
        except Exception as e:
            problems.append(f"[{fid}] Unexpected error checking {record.path}: {e}")

    return len(problems) == 0, problems