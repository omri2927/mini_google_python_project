import re
from itertools import zip_longest
from pathlib import Path
import os
import csv
import json
import xml.etree.ElementTree as et


# text files constants
MAX_TEXT_FILE_BYTES = 8 * 1_000_000
MAX_TEXT_UNITS = 500
MAX_TEXT_UNIT_LEN = 200

# csv constants
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

# xml constants
MAX_XML_FILE_BYTES = 10 * 1_000_000
MAX_XML_UNITS = 400
MAX_XML_UNIT_LEN = 180
MAX_XML_DEPTH = 8
MAX_XML_CHILDREN_PER_NODE = 20
MAX_XML_ATTRS_PER_NODE = 15
MAX_XML_NODE_TAILS = 2
MAX_XML_UNITS_PER_NODE = 15
MAX_XML_TAG_LEN = 50
MAX_XML_PATH_LEN = 220


def get_file_extension(path: str) -> str:
    return Path(path).suffix

def clamp_units(units: list[str], *, max_units: int, max_len: int) -> list[str]:
    return [re.sub(r'[\r\n\t]', ' ', str(unit[:max_len]).strip()) for unit in units][:max_units]


def extract_plaintext_units(path: str) -> list[str]:
    if not path or os.path.getsize(path) > MAX_TEXT_FILE_BYTES:
        return []

    units_list = []
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as file:
        for line in file:
            if len(units_list) == MAX_TEXT_UNITS:
                break
            formatted_line = line[:-1].rstrip()[:MAX_TEXT_UNIT_LEN]
            if formatted_line:
                units_list.append(formatted_line)

    return clamp_units(units_list, max_units=MAX_TEXT_UNITS, max_len=MAX_TEXT_UNIT_LEN)


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


def format_csv_row(headers: list[str], row: list[str],
                   case_sensitive: bool) -> str:
    MISSING_HEADER = object()
    parts = []

    for i, (h, v) in enumerate(zip_longest(headers, row, fillvalue=MISSING_HEADER)):
        h_display = h.strip()
        if not case_sensitive:
            h_display = h_display.casefold()
        if v is MISSING_HEADER:
            parts.append(f"{h_display}: ''")
        elif h is MISSING_HEADER:
            parts.append(f"col{i + 1}: {v.strip()}")
        else:
            parts.append(f"{h_display}: {v.strip()}")

    return " | ".join(parts)

def extract_csv_units(path: str, case_sensitive: bool) -> list[str]:
    sample = read_csv_sample_rows(path)
    has_header = detect_csv_has_header(sample)
    headers, values = parse_csv_rows(path, has_header=has_header)
    formatted_csv_units = [format_csv_row(headers, row,
                                          case_sensitive=case_sensitive) for row in values]

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

def _flatten_json(data: object, *, prefix: str, depth: int,
                  out: list[str], case_sensitive: bool) -> None:
    if len(out) == MAX_JSON_UNITS or depth == MAX_JSON_DEPTH:
        return

    if isinstance(data, dict):
        items_used = 0
        for key in sorted(data.keys()):
            if items_used == MAX_JSON_DICT_ITEMS:
                return

            string_key = str(key).strip()[:MAX_JSON_KEY_LEN]
            if not case_sensitive:
                string_key = string_key.casefold()

            if not prefix:
                new_prefix = string_key
            else:
                new_prefix = prefix + "." + string_key

            items_used += 1

            _flatten_json(data[key], prefix=new_prefix, depth=depth+1, out=out,
                          case_sensitive=case_sensitive)
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

            _flatten_json(value, prefix=new_prefix, depth=depth+1, out=out,
                          case_sensitive=case_sensitive)
    else:
        if not prefix:
            out.append(f"root: {_json_value_to_text(data)}")
        else:
            out.append(f"{prefix}: {_json_value_to_text(data)}")

def extract_json_units(path: str, case_sensitive: bool) -> list[str]:
    data = _load_json_data(path)

    if data is None:
        return []

    out = []
    _flatten_json(data=data, prefix="",
                  depth=0, out=out, case_sensitive=case_sensitive)
    return clamp_units(out, max_units=MAX_JSON_UNITS, max_len=MAX_JSON_UNIT_LEN)

def _load_xml_root(path: str) -> et.Element | None:
    if not path or os.path.getsize(path) > MAX_XML_FILE_BYTES:
        return None

    try:
        with open(path, mode='r', encoding='utf-8-sig') as file:
            tree = et.parse(file)
            return tree.getroot()

    except FileNotFoundError:
        print(f"Error: File not found at {path}")
    except et.ParseError as e:
        print(f"Invalid XML: {e}")
    except UnicodeDecodeError:
        print("Error: File is not valid UTF-8.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return None

def _xml_clean_text(text: str) -> str:
    text = re.sub(r'[\r\n\t]', ' ', str(text).strip())

    if "  " in text:
        text = " ".join(text.split())

    if not text:
        return ""

    return text

def _xml_clean_tag(tag: str, case_sensitive: bool) -> str:
    if "}" in tag:
        tag = tag.split("}")[-1]

    tag = tag[:MAX_XML_TAG_LEN].strip()
    return tag if case_sensitive else tag.casefold()

def _flatten_xml(root: et.Element, *, out: list[str], depth: int,
                 prefix: str = "", case_sensitive: bool) -> None:
    if len(out) == MAX_XML_UNITS or depth == MAX_XML_DEPTH:
        return

    count_node_units = 0

    current_path = prefix if prefix else _xml_clean_tag(root.tag,
                                                        case_sensitive=case_sensitive)

    cleaned_root_text = _xml_clean_text(root.text)
    if cleaned_root_text:
        out.append(f"{current_path[:MAX_XML_PATH_LEN]}: {cleaned_root_text}")
        count_node_units += 1

    total_attrs = 0
    for attr_name, attr_value in sorted(root.attrib.items()):
        if count_node_units == MAX_XML_UNITS_PER_NODE:
            break

        if len(out) == MAX_XML_UNITS:
            return

        if total_attrs == MAX_XML_ATTRS_PER_NODE:
            break

        clean_attr_name = _xml_clean_tag(attr_name, case_sensitive=case_sensitive)
        cleaned_attr_value = _xml_clean_text(attr_value)

        if not clean_attr_name or not cleaned_attr_value:
            continue
        else:
            out.append(f"{current_path}@{clean_attr_name}: {cleaned_attr_value}")
            total_attrs += 1
            count_node_units += 1

    if len(root) > 0:
        children_passed: dict[str, int] = dict()
        total_children = 0
        count_tails = 0
        for child in root:
            tag = _xml_clean_tag(child.tag,
                                 case_sensitive=case_sensitive)

            if total_children == MAX_XML_CHILDREN_PER_NODE:
                break

            if tag in children_passed.keys():
                children_passed[tag] += 1
            else:
                children_passed[tag] = 1

            total_children += 1

            new_prefix = f"{current_path}.{tag}[{children_passed[tag]}]"
            _flatten_xml(child, out=out, depth=depth+1,
                         prefix=new_prefix, case_sensitive=case_sensitive)

            if count_node_units < MAX_XML_UNITS_PER_NODE and count_tails < MAX_XML_NODE_TAILS:
                tail_data = _xml_clean_text(child.tail) if child.tail else ""
                if tail_data:
                    out.append(f"{current_path}#tail: {tail_data}")
                    count_node_units += 1
                    count_tails += 1

            if len(out) == MAX_XML_UNITS:
                return
    else:
        return

def extract_xml_units(path: str, case_sensitive: bool) -> list[str]:
    root = _load_xml_root(path)
    units: list[str] = []

    if root is None:
        return []

    _flatten_xml(root=root, out=units, depth=0,
                 prefix="", case_sensitive=case_sensitive)
    return clamp_units(units=units, max_units=MAX_XML_UNITS, max_len=MAX_XML_UNIT_LEN)


def extract_units_by_extension(path: str, ext: str, *, case_sensitive: bool) -> list[str]:
    ext = ext.lower()

    if ext in {".txt", ".log", ".py", ".md"}:
        return extract_plaintext_units(path)
    elif ext == ".csv":
        return extract_csv_units(path, case_sensitive=case_sensitive)
    elif ext == ".json":
        return extract_json_units(path, case_sensitive=case_sensitive)
    elif ext == ".xml":
        return extract_xml_units(path, case_sensitive=case_sensitive)
    else:
        return []
