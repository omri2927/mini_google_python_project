import os
from typing import Iterable

from core.models import FileRecord, FileType, Hit
from core import tokenizer

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
        else:
            file_type = FileType.MD

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
        for line_no, line in iter_lines(file_record.path):
            tokens = tokenizer.tokenize_line(
                line,
                min_length=min_length,
                stopwords=stopwords,
                keep_numbers=keep_numbers,
            )

            for token in tokens:
                hits = index.setdefault(token, [])

                # Avoid duplicates: same token, same file, same line
                already_exists = any(
                    h.file_id == file_id and h.line_no == line_no for h in hits
                )
                if already_exists:
                    continue

                hits.append(Hit(file_id=file_id, line_no=line_no, start=-1, end=-1))

    return index

