import os
from typing import Iterable
from collections import Counter

from core.models import FileRecord, FileType, Hit
from core import tokenizer, extractors

# Return all searchable files under root_dir
def scan_files(root_dir: str, extensions: set[str]) -> list[FileRecord]:
    file_records_list: list[FileRecord] = []

    if not os.path.isdir(root_dir):
        raise NotADirectoryError(f"Not a directory: {root_dir}")

    for filename in os.listdir(root_dir):
        file_path = os.path.join(root_dir, filename)
        ext = os.path.splitext(filename)[1].casefold()

        if not os.path.isfile(file_path) or ext not in extensions:
            continue

        if ext == ".txt":
            file_type = FileType.TXT
        elif ext == ".log":
            file_type = FileType.LOG
        elif ext == ".py":
            file_type = FileType.PY
        elif ext == ".md":
            file_type = FileType.MD
        elif ext == ".csv":
            file_type = FileType.CSV
        elif ext == ".json":
            file_type = FileType.JSON
        else:
            file_type = FileType.XML

        file_records_list.append(FileRecord(path=file_path, size=int(os.path.getsize(file_path)),
                                            mtime=float(os.path.getmtime(file_path)), filetype=file_type))

    return file_records_list

def build_unit_store_incremental(
    files_to_process: dict[int, FileRecord],
    *,
    case_sensitive: bool
) -> dict[int, list[str]]:
    incremental_units: dict[int, list[str]] = {}

    for file_id, file in files_to_process.items():
        ext = os.path.splitext(file.path)[1].casefold()
        file_units = extractors.extract_units_by_extension(
            path=file.path,
            ext=ext,
            case_sensitive=case_sensitive
        )
        incremental_units[file_id] = file_units

    return incremental_units

# Build an inverted index: token -> list of hits.
def build_index(
        files: dict[int, FileRecord],  # Changed from dict[int, list[FileRecord]]
        *,
        unit_store: dict[int, list[str]],
        min_length: int = 2,
        stopwords: set[str] | None = None,
        keep_numbers: bool = True,
) -> dict[str, list[Hit]]:
    index: dict[str, list[Hit]] = {}

    # Iterate using .items() to get the actual assigned file_id
    for file_id, file_record in files.items():
        # Safeguard: check if the file_id exists in the unit_store
        units = unit_store.get(file_id, [])

        for unit_index, unit in enumerate(units):
            tokens = tokenizer.tokenize_unit(
                unit=unit,
                min_length=min_length,
                stopwords=stopwords,
                keep_numbers=keep_numbers,
            )

            # Efficiently count tokens in this unit
            token_counts = Counter(tokens)
            for token, count in token_counts.items():
                if token not in index:
                    index[token] = []

                # Append the hit using the consistent file_id
                index[token].append(Hit(
                    file_id=file_id,
                    unit_index=unit_index,
                    count=count
                ))

    return index

def build_casefold_index(index: dict[str, list[Hit]]) -> dict[str, list[Hit]]:
    """
    Builds an optimized version of the inverted index where all tokens are lowercased.
    This should be called once after build_index or load_index to speed up
    case-insensitive searches.
    """
    ci: dict[str, list[Hit]] = dict()

    for token, hits in index.items():
        cf_token = token.casefold()

        if cf_token not in ci:
            ci[cf_token] = []

        # We extend so that if 'Python' and 'python' both exist,
        # their hit lists are merged into the 'python' key.
        ci[cf_token].extend(hits)

    return ci

def assign_file_ids(
    *,
    existing_id_by_path: dict[str, int],
    scanned_files: list[FileRecord]
) -> tuple[
    dict[int, FileRecord],
    dict[str, int]
]:
    new_files_by_id: dict[int, FileRecord] = dict()
    new_id_by_path: dict[str, int] = dict()

    current_max_id = max(existing_id_by_path.values(), default=-1)

    for file in scanned_files:
        path = file.path

        if path in existing_id_by_path:
            file_id = existing_id_by_path[path]
        else:
            current_max_id += 1
            file_id = current_max_id

        new_id_by_path[path] = file_id
        new_files_by_id[file_id] = file

    return new_files_by_id, new_id_by_path


def diff_files(
    *,
    old_files_by_id: dict[int, FileRecord],
    new_files_by_id: dict[int, FileRecord]
) -> tuple[
    set[int],  # unchanged
    set[int],  # modified
    set[int],  # deleted
    set[int],  # added
]:
    unchanged, modified, added = set(), set(), set()

    MTIME_TOLERANCE = 2.0
    for file_id, file in new_files_by_id.items():
        if file_id in old_files_by_id:
            old_file = old_files_by_id[file_id]

            is_same_size = old_file.size == file.size
            is_same_mtime = abs(old_file.mtime - file.mtime) <= MTIME_TOLERANCE

            if is_same_size and is_same_mtime:
                unchanged.add(file_id)
            else:
                modified.add(file_id)
        else:
            added.add(file_id)

    deleted = set(old_files_by_id.keys()) - set(new_files_by_id.keys())

    return unchanged, modified, deleted, added

def rebuild_index_incremental(
    *,
    old_files_by_id: dict[int, FileRecord],
    old_id_by_path: dict[str, int],
    old_unit_store: dict[int, list[str]],
    old_index: dict[str, list[Hit]],
    new_scan_files: list[FileRecord],
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    case_sensitive: bool = False
) -> tuple[
    dict[int, FileRecord],
    dict[str, int],
    dict[int, list[str]],
    dict[str, list[Hit]]
]:
    new_unit_store: dict[int, list[str]] = dict()

    new_files_by_id, new_id_by_path = assign_file_ids(
                                      existing_id_by_path=old_id_by_path,
                                      scanned_files=new_scan_files)

    unchanged, modified, deleted, added = diff_files(
                                          old_files_by_id=old_files_by_id,
                                          new_files_by_id=new_files_by_id)

    for fid in unchanged:
        new_unit_store[fid] = old_unit_store[fid]

    ids_to_process = added | modified
    files_to_process = {fid: new_files_by_id[fid] for fid in ids_to_process}
    processed_units = build_unit_store_incremental(
        files_to_process,
        case_sensitive=case_sensitive
    )

    new_unit_store.update(processed_units)

    final_index = build_index(
        new_files_by_id,  # Must be dict[int, FileRecord]
        unit_store=new_unit_store,
        min_length=min_length,
        stopwords=stopwords,
        keep_numbers=keep_numbers
    )

    return new_files_by_id, new_id_by_path, new_unit_store, final_index

def remove_file_from_index(*, index: dict[str, list[Hit]], file_id: int) -> None:
    tokens_to_remove = []

    for token, hits in index.items():
        new_hits = [hit for hit in hits if hit.file_id != file_id]

        if len(new_hits) != len(hits):
            index[token] = new_hits

        if not index[token]:
            tokens_to_remove.append(token)

    for token in tokens_to_remove:
        del index[token]

def add_file_to_index(
    *,
    index: dict[str, list[Hit]],
    file_id: int,
    units: list[str],
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True
) -> None:
    for unit_index, unit in enumerate(units):
        # 1. Generate tokens for the specific unit
        tokens = tokenizer.tokenize_unit(
            unit=unit,
            min_length=min_length,
            stopwords=stopwords,
            keep_numbers=keep_numbers,
        )

        # 2. Count occurrences within this unit to create compact Hits
        token_counts = Counter(tokens)

        # 3. Update the global index
        for token, count in token_counts.items():
            if token not in index:
                index[token] = []

            # Append the new Hit record
            index[token].append(Hit(
                file_id=file_id,
                unit_index=unit_index,
                count=count
            ))
