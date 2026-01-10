import re

from core import tokenizer

# Return up to max_snippets lines containing any query token.
def make_snippets(
    path: str,
    query_tokens: list[str],
    *,
    max_snippets: int = 3,
    max_len: int = 180,
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    case_sensitive: bool = False
) -> list[str]:
    lines_matched: list[str] = []
    query_tokens = set(query_tokens)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            all_line_tokens_list = tokenizer.tokenize_line(line, min_length=min_length,
                                                           stopwords=stopwords, keep_numbers=keep_numbers,
                                                           case_sensitive=case_sensitive)
            for token in all_line_tokens_list:
                if token in query_tokens:
                    if len(line) > max_len:
                        line = line[:max_len]
                    lines_matched.append(line)
                    break

            if len(lines_matched) == max_snippets:
                break

    return lines_matched

# Return up to max_snippets lines that contain query_text (case-sensitive).
def make_exact_snippets(
    path: str,
    query_text: str,
    *,
    max_snippets: int = 3,
    max_len: int = 180,
    case_sensitive: bool = False
) -> list[str]:
    snippets_list: list[str] = list()

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean_line = line.strip()

            # Decide if we match based on case
            if case_sensitive:
                match_found = query_text in clean_line
            else:
                # We check lowercase versions but DO NOT modify the original clean_line
                match_found = query_text.lower() in clean_line.lower()

            if match_found:
                # Add the ORIGINAL line (with original casing) to the results
                snippets_list.append(clean_line[:max_len])

            if len(snippets_list) == max_snippets:
                break

    return snippets_list

def make_snippets_contains(
    path: str,
    query_tokens: list[str],
    *,
    max_snippets: int = 3,
    max_len: int = 180,
    case_sensitive: bool = False,
) -> list[str]:
    snippets_list: list[str] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            for token in query_tokens:
                if case_sensitive:
                    if token in line:
                        snippets_list.append(line[:max_len])
                        break
                else:
                    if token.lower() in line.lower():
                        snippets_list.append(line[:max_len])
                        break

            if len(snippets_list) == max_snippets:
                break

    return snippets_list

def make_regex_snippets(
    path: str,
    compiled_re: re.Pattern,
    *,
    max_snippets: int = 3,
    max_len: int = 180,
    case_sensitive: bool = False
) -> list[str]:
    snippets_list: list[str] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean_line = line.strip()

            if compiled_re.search(clean_line):
                snippets_list.append(clean_line[:max_len])

            if len(snippets_list) == max_snippets:
                break

    return snippets_list