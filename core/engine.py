from models import FileRecord, Hit

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
) -> tuple[dict[int, FileRecord], dict[str, int],
    dict[int, list[str]], dict[str, list[Hit]]]:
    pass