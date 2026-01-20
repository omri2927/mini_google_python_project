import re
from itertools import zip_longest
from pathlib import Path
import os
import csv
import json

MAX_CSV_HEADER_LENGTH = 40
MAX_CSV_UNITS = 500
MAX_CSV_UNIT_LEN = 130

# json constants
MAX_JSON_FILE_BYTES = 10 * 1_000_000
MAX_JSON_UNITS = 500
MAX_JSON_UNIT_LEN = 220
MAX_JSON_DEPTH = 10
MAX_JSON_LIST_ITEMS = 100
MAX_JSON_DICT_ITEMS = 150
MAX_JSON_KEY_LEN = 125

def get_file_extension(path: str) -> str:
    return Path(path).suffix

def clamp_units(units: list[str], *, max_units: int, max_len: int) -> list[str]:
    return [re.sub(r'[\r\n\t]', ' ', str(unit[:max_len]).strip()) for unit in units][:max_units]


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
    formatted_csv_units = [format_csv_row(headers, row) for row in values]

    return clamp_units(formatted_csv_units, max_units=MAX_CSV_UNITS, max_len=MAX_CSV_UNIT_LEN)

def _load_json_data(path: str) -> object | None:
    if os.path.getsize(path) > MAX_JSON_FILE_BYTES:
        return None

    try:
        with open(path, mode='r', encoding='utf-8-sig') as file:
            # json.load() validates structural correctness while parsing
            return json.load(file)

    except FileNotFoundError:
        print(f"Error: File not found at {path}")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}")
    except UnicodeDecodeError:
        print("Error: File is not valid UTF-8.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return None

def _json_value_to_text(value: object) -> str:
    if value is None:
        return "null"
    elif value is True:
        return "true"
    elif value is False:
        return "false"
    elif isinstance(value, (int, float)):
        return str(value)

    return re.sub(r'[\r\n\t]', ' ', str(value).strip())

def _flatten_json(data: object, *, prefix: str, depth: int, out: list[str]) -> None:
    if len(out) == MAX_JSON_UNITS or depth == MAX_JSON_DEPTH:
        return

    if isinstance(data, dict):
        items_used = 0
        for key in sorted(data.keys()):
            if items_used == MAX_JSON_DICT_ITEMS:
                return

            string_key = str(key).strip()[:MAX_JSON_KEY_LEN]

            if not prefix:
                new_prefix = string_key
            else:
                new_prefix = prefix + "." + string_key

            items_used += 1

            _flatten_json(data[key], prefix=new_prefix, depth=depth+1, out=out)
    elif isinstance(data, list):
        items_used = 0
        for index, value in enumerate(data):
            if items_used == MAX_JSON_LIST_ITEMS:
                return

            if not prefix:
                new_prefix = f"[{index}]"
            else:
                new_prefix = f"{prefix}[{index}]"

            items_used += 1

            _flatten_json(value, prefix=new_prefix, depth=depth+1, out=out)
    else:
        if not prefix:
            out.append(f"root: {_json_value_to_text(data)}")
        else:
            out.append(f"{prefix}: {_json_value_to_text(data)}")

def extract_json_units(path: str) -> list[str]:
    data = _load_json_data(path)

    if data is None:
        return []

    out = []
    _flatten_json(data=data, prefix="", depth=0, out=out)
    return clamp_units(out, max_units=MAX_JSON_UNITS, max_len=MAX_JSON_UNIT_LEN)


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



