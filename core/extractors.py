from itertools import zip_longest
from pathlib import Path
import csv

MAX_CSV_HEADER_LENGTH = 50


def get_file_extension(path: str) -> str:
    return Path(path).suffix


def extract_plaintext_units(path: str) -> list[str]:
    pass

def _is_number(string: str):
    if string.replace('.', '', 1).isdigit() or string.replace(',', '', 1).isdigit():
        return True

    return False

def read_csv_sample_rows(path: str, *, max_rows: int = 20) -> list[list[str]]:
    sample: list[list[str]] = []
    with open(path, mode='r', newline='', encoding='utf-8-sig') as file:
        reader = csv.reader(file)

        for row in reader:
            if len(sample) == max_rows:
                break
            sample.append(row)

    return sample


def detect_csv_has_header(sample_rows: list[list[str]]) -> bool:
    if not sample_rows or len(sample_rows) < 2:
        return False

    first_row = sample_rows[0]
    second_row = sample_rows[1]

    if len(set(first_row)) != len(first_row):
        return False

    for cell in first_row:
        if len(cell.strip()) > MAX_CSV_HEADER_LENGTH or len(cell.strip()) == 0:
            return False

    for h, v in zip(first_row, second_row):
        h_is_num = _is_number(h)
        v_is_num = _is_number(v)

        if v_is_num and not h_is_num:
            return True

    if first_row == second_row:
        return False

    return True


def parse_csv_rows(path: str, has_header: bool) -> tuple[list[str], list[list[str]]]:
    headers: list[str] = []
    values: list[list[str]] = []

    with open(path, mode='r', newline='', encoding='utf-8-sig') as file:
        reader = csv.reader(file)

        try:
            if has_header:
                headers = next(reader)
            else:
                values.append(next(reader))
        except StopIteration:
            return [], []

        for row in reader:
            values.append(row)

    if not values:
        return [], []

    if not has_header:
        for i in range(1, max(len(row) for row in values) + 1):
            headers.append(f"col{i}")

    return headers, values


def format_csv_row(headers: list[str], row: list[str]) -> str:
    MISSING_HEADER = object()
    parts = []

    for i, (h, v) in enumerate(zip_longest(headers, row, fillvalue=MISSING_HEADER)):
        if v is MISSING_HEADER:
            parts.append(f"{h.strip()}: ''")
        elif h is MISSING_HEADER:
            parts.append(f"col{i + 1}: {v.strip()}")
        else:
            parts.append(f"{h.strip()}: {v.strip()}")

    return " | ".join(parts)


def extract_csv_units(path: str) -> list[str]:
    sample = read_csv_sample_rows(path)
    has_header = detect_csv_has_header(sample)
    headers, values = parse_csv_rows(path, has_header=has_header)
    return [format_csv_row(headers, row) for row in values]


def extract_json_units(path: str) -> list[str]:
    pass


def extract_xml_units(path: str) -> list[str]:
    pass


def extract_units_by_extension(path: str, ext: str, *, case_sensitive: bool) -> list[str]:
    ext = ext.lower()

    if ext in {".txt", ".log", ".py", ".md"}:
        return extract_plaintext_units(path)
    elif ext == ".csv":
        return extract_csv_units(path)
    elif ext == ".json":
        return extract_json_units(path)
    elif ext == ".xml":
        return extract_xml_units(path)
    else:
        return []


def clamp_units(units: list[str], *, max_units: int, max_len: int) -> list[str]:
    pass
