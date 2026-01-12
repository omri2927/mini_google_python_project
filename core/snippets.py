import re

from core import tokenizer

NUM_OF_SEPARATORS_BETWEEN_LINES = 50

def token_and_matching(line: str, q_set: set[str], case_sensitive: bool):
    all_line_tokens_list = tokenizer.tokenize_line(line, case_sensitive=case_sensitive)

    for token in all_line_tokens_list:
        if not case_sensitive:
            token = token.lower()
        if token in q_set:
            return True

    return False

def token_contains_matching(line: str, q_set: set[str], case_sensitive: bool):
    search_line = line if case_sensitive else line.lower()
    for token in q_set:
        if token in search_line:
            return True

    return False

def exact_matching(line: str, query_text: str, case_sensitive: bool):
    if case_sensitive:
        if query_text in line:
            return True
    else:
        if query_text in line.lower():
            return True

    return False

def regex_matching(line, compiled_re: re.Pattern):
    if compiled_re.search(line):
        return True

    return False

def _find_matching_line_indexes(lines: list[str], *, mode: str, query_tokens: list[str] | None,
                                query_text: str | None, compiled_re: re.Pattern | None,
                                case_sensitive: bool) -> list[int]:
    matching_lines_list: list[int] = []

    q_set = set()
    if query_tokens:
        if not case_sensitive:
            q_set = {tok.lower() for tok in query_tokens}
        else:
            q_set = set(query_tokens)
    elif mode != "regex" and mode != "exact":
        return []

    if query_text:
        query_text = query_text if case_sensitive else query_text.lower()
    elif mode == "exact":
        return []

    for i, line in enumerate(lines):
        if mode == "tokens":
            if token_and_matching(line=line, q_set=q_set, case_sensitive=case_sensitive):
                matching_lines_list.append(i)
        elif mode == "contains":
            if token_contains_matching(line=line, q_set=q_set, case_sensitive=case_sensitive):
                matching_lines_list.append(i)
        elif mode == "exact":
            if query_text:
                if exact_matching(line=line, query_text=query_text, case_sensitive=case_sensitive):
                    matching_lines_list.append(i)
        elif mode == "regex":
            if compiled_re:
                if regex_matching(line=line, compiled_re=compiled_re):
                    matching_lines_list.append(i)

    matching_lines_list.sort()
    return matching_lines_list

def _build_context_windows(match_indexes: list[int], *, total_lines: int,
                           before: int, after: int) -> list[tuple[int, int]]:
    matching_ranges_list = []
    for match in match_indexes:
        start = max(0, match - before)
        end = min(total_lines, match + after + 1)

        if not matching_ranges_list:
            matching_ranges_list.append([start, end])
        else:
            last_window = matching_ranges_list[-1]

            if start <= last_window[1]:
                last_window[1] = max(last_window[1], end)
            else:
                matching_ranges_list.append([start, end])

    return [(m[0], m[1]) for m in matching_ranges_list]

def _format_snippet_block(lines: list[str], *, start: int, end: int, max_len: int) -> str:
    block_to_return = f"Lines {start}-{end}" if start != end else f"Line {start}"

    if start >= len(lines):
        return ""
    end = min(end, len(lines)-1)
    start = max(0, start)

    lines_to_show: list[str] = []
    for i in range(start-1, end):
        lines_to_show.append(f" {lines[i][:max_len]}")

    content = "\n".join(lines_to_show)
    block_to_return += f"\n{content}"
    block_to_return += f"\n{'-'*NUM_OF_SEPARATORS_BETWEEN_LINES}\n"

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