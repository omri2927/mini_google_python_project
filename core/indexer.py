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
        ext = os.path.splitext(filename)[1].lower()

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

# Yield (line_no, line_text) for a file without loading it entirely.
def iter_lines(path: str) -> Iterable[tuple[int, str]]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f, start=1):
            yield line_no, line.rstrip("\n")

# Build an inverted index: token -> list of hits.
def build_index(
    files: list[FileRecord],
    *,
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
) -> dict[str, list[Hit]]:
    index: dict[str, list[Hit]] = {}

    for file_id, file_record in enumerate(files):
        ext = os.path.splitext(file_record.path)[1].lower()
        file_units: list[str] = extractors.extract_units_by_extension(path=file_record.path, ext=ext, case_sensitive=False)

        for unit_index, unit in enumerate(file_units):
            tokens = tokenizer.tokenize_unit(
                unit=unit,
                min_length=min_length,
                stopwords=stopwords,
                keep_numbers=keep_numbers,
            )

            token_counts = Counter(tokens)
            for token, count in token_counts.items():
                if token not in index:
                    index[token] = []

                index[token].append(Hit(file_id=file_id, unit_index=unit_index, count=count))

    return index

