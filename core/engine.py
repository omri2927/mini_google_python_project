from pathlib import Path

from core.models import FileRecord, Hit
from core import extractors, indexer

def rebuild_index_incremental(
    *,
    old_files_by_id: dict[int, FileRecord],
    old_id_by_path: dict[str, int],
    old_unit_store: dict[int, list[str]],
    old_index: dict[str, list[Hit]],
    root_dir: str,
    extensions: set[str],
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    case_sensitive: bool = False
) -> tuple[dict[int, FileRecord],
    dict[str, int],
    dict[int, list[str]],
    dict[str, list[Hit]],
    dict[str, list[Hit]]]:
    files = indexer.scan_files(root_dir=root_dir,
                               extensions=extensions)
    new_files_by_id, new_id_by_path = indexer.assign_file_ids(
        existing_id_by_path=old_id_by_path, scanned_files=files)

    unchanged, modified, deleted, added = indexer.diff_files(
                                          old_files_by_id=old_files_by_id,
                                          new_files_by_id=new_files_by_id)


    new_unit_store: dict[int, list[str]] = dict()

    for fid in unchanged:
        new_unit_store[fid] = old_unit_store[fid]

    ids_to_process = added | modified
    files_to_process = {fid: new_files_by_id[fid] for fid in ids_to_process}

    if files_to_process:
        processed_units = indexer.build_unit_store_incremental(
            files_to_process=files_to_process,
            case_sensitive=case_sensitive
        )
        new_unit_store.update(processed_units)

    ids_to_delete = deleted | modified

    new_index = deepcopy(old_index)
    for id_to_delete in ids_to_delete:
        indexer.remove_file_from_index(index=new_index,
                                       file_id=id_to_delete)

    for id_to_add in files_to_process:
        indexer.add_file_to_index(index=new_index,
                                  file_id=id_to_add,
                                  units=new_unit_store[id_to_add],
                                  min_length=min_length,
                                  stopwords=stopwords,
                                  keep_numbers=keep_numbers)

    new_casefold_index = indexer.build_casefold_index(old_index)

    return new_files_by_id, new_id_by_path, \
           new_unit_store, new_index, new_casefold_index

def build_index_fresh(
    *,
    root_dir: str,
    extensions: set[str],
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    case_sensitive: bool = False
) -> tuple[
    dict[int, FileRecord],
    dict[str, int],
    dict[int, list[str]],
    dict[str, list[Hit]],
    dict[str, list[Hit]]
]:
    files: list[FileRecord] = indexer.scan_files(root_dir=root_dir,
                                     extensions=extensions)

    files_by_id, ids_by_path = indexer.assign_file_ids(existing_id_by_path={},
                                                       scanned_files=files)

    unit_store: dict[int, list[str]] = indexer.build_unit_store_incremental(
                                         files_to_process=files_by_id,
                                         case_sensitive=case_sensitive)

    index = indexer.build_index(files=files_by_id, unit_store=unit_store,
                                min_length=min_length, stopwords=stopwords,
                                keep_numbers=keep_numbers)
    casefold_index = indexer.build_casefold_index(index=index)

    return files_by_id, ids_by_path,\
           unit_store, index, casefold_index