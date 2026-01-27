import re

from core import tokenizer

NUM_OF_SEPARATORS_BETWEEN_UNITS = 120
MAX_UNITS_IN_BLOCK = 8

def token_and_matching(unit: str, q_set: set[str], case_sensitive: bool,
                       min_length: int = 2, stopwords: set[str] | None = None, keep_numbers: bool = True,):
    all_unit_tokens_list = tokenizer.tokenize_unit(unit,
                                                   min_length=min_length,
                                                   stopwords=stopwords,
                                                   keep_numbers=keep_numbers,
                                                   case_sensitive=case_sensitive)

    for token in all_unit_tokens_list:
        if not case_sensitive:
            token = token.casefold()
        if token in q_set:
            return True

    return False

def token_contains_matching(unit: str, q_set: set[str], case_sensitive: bool):
    search_unit = unit if case_sensitive else unit.casefold()
    for token in q_set:
        if token in search_unit:
            return True

    return False

def exact_matching(unit: str, query_text: str, case_sensitive: bool):
    if case_sensitive:
        if query_text in unit:
            return True
    else:
        if query_text in unit.casefold():
            return True

    return False

def regex_matching(unit, compiled_re: re.Pattern):
    if compiled_re.search(unit):
        return True

    return False

def _find_matching_unit_indexes(units: list[str], *, mode: str, query_tokens: list[str] = None,
                                query_text: str = None, compiled_re: re.Pattern = None,
                                min_length: int = 2, stopwords: set[str] = None, keep_numbers: bool = True,
                                case_sensitive: bool = False) -> list[int]:
    matching_units_list: list[int] = []

    q_set = set()
    if query_tokens:
        if not case_sensitive:
            q_set = {tok.casefold() for tok in query_tokens}
        else:
            q_set = set(query_tokens)
    elif mode != "regex" and mode != "exact":
        return []

    if query_text:
        query_text = query_text if case_sensitive else query_text.casefold()
    elif mode == "exact":
        return []

    for i, unit in enumerate(units):
        if mode == "tokens":
            if token_and_matching(unit=unit, q_set=q_set, case_sensitive=case_sensitive,
                                  min_length=min_length, stopwords=stopwords, keep_numbers=keep_numbers):
                matching_units_list.append(i)
        elif mode == "contains":
            if token_contains_matching(unit=unit, q_set=q_set, case_sensitive=case_sensitive):
                matching_units_list.append(i)
        elif mode == "exact":
            if query_text:
                if exact_matching(unit=unit, query_text=query_text, case_sensitive=case_sensitive):
                    matching_units_list.append(i)
        elif mode == "regex":
            if compiled_re:
                if regex_matching(unit=unit, compiled_re=compiled_re):
                    matching_units_list.append(i)

    matching_units_list.sort()
    return matching_units_list

def _build_context_windows(match_indexes: list[int], *, total_units: int,
                           before: int, after: int) -> list[tuple[int, int]]:
    merged: list[list[int]] = []

    for match in match_indexes:
        start = max(0, match - before)
        end = min(total_units, match + after + 1)

        if not merged:
            merged.append([start, end])
        else:
            last = merged[-1]
            if start <= last[1]:
                last[1] = max(last[1], end)
            else:
                merged.append([start, end])

    final_windows: list[tuple[int, int]] = []
    for start, end in merged:
        while end - start > MAX_UNITS_IN_BLOCK:
            final_windows.append((start, start + MAX_UNITS_IN_BLOCK))
            start += MAX_UNITS_IN_BLOCK
        final_windows.append((start, end))

    return final_windows

def _format_snippet_block(units: list[str], *, start: int, end: int, max_len: int) -> str:
    display_start = start + 1
    safe_end = min(end, len(units))
    display_end = safe_end
    block_to_return = f"Units {display_start}-{display_end}" if display_start != display_end\
        else f"Unit {display_start}"

    if not units or start >= len(units):
        return ""

    units_to_show: list[str] = []
    for i in range(start, safe_end):
        units_to_show.append(f" {units[i][:max_len].rstrip()}")

    content = "\n".join(units_to_show)
    block_to_return += f"\n{content}"
    block_to_return += f"\n{'-'*NUM_OF_SEPARATORS_BETWEEN_UNITS}\n"

    return block_to_return

def make_snippets(
    units: list[str],
    query_tokens: list[str],
    *,
    max_snippets: int = 3,
    max_len: int = 180,
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    case_sensitive: bool = False,
    context_before: int = 1,
    context_after: int = 1
) -> list[str]:
    snippets_list = []

    matching_units_indexes = _find_matching_unit_indexes(units=units, mode="tokens",
                                                         query_tokens=query_tokens,
                                                         min_length=min_length,
                                                         stopwords=stopwords,
                                                         keep_numbers=keep_numbers,
                                                         case_sensitive=case_sensitive)

    windows_ranges_list = _build_context_windows(match_indexes=matching_units_indexes,
                                                 total_units=len(units),
                                                 before=context_before, after=context_after)

    for start, end in windows_ranges_list:
        snippets_list.append(_format_snippet_block(units=units,
                                                   start=start, end=end,
                                                   max_len=max_len))

        if len(snippets_list) == max_snippets:
            break

    return snippets_list

def make_snippets_contains(
    units: list[str],
    query_tokens: list[str],
    *,
    max_snippets: int = 3,
    max_len: int = 180,
    case_sensitive: bool = False,
    context_before: int = 1,
    context_after: int = 1
) -> list[str]:
    snippets_list = []

    matching_units_indexes = _find_matching_unit_indexes(units=units, mode="contains",
                                                         query_tokens=query_tokens,
                                                         case_sensitive=case_sensitive)

    windows_ranges_list = _build_context_windows(match_indexes=matching_units_indexes,
                                                 total_units=len(units),
                                                 before=context_before, after=context_after)

    for start, end in windows_ranges_list:
        snippets_list.append(_format_snippet_block(units=units,
                                                   start=start, end=end,
                                                   max_len=max_len))

        if len(snippets_list) == max_snippets:
            break

    return snippets_list

def make_exact_snippets(
    units: list[str],
    query_text: str,
    *,
    max_snippets: int = 3,
    max_len: int = 180,
    case_sensitive: bool = False,
    context_before: int = 1,
    context_after: int = 1
) -> list[str]:
    snippets_list = []

    matching_units_indexes = _find_matching_unit_indexes(units=units, mode="exact",
                                                         query_text=query_text,
                                                         case_sensitive=case_sensitive)

    windows_ranges_list = _build_context_windows(match_indexes=matching_units_indexes,
                                                 total_units=len(units),
                                                 before=context_before, after=context_after)

    for start, end in windows_ranges_list:
        snippets_list.append(_format_snippet_block(units=units,
                                                   start=start, end=end,
                                                   max_len=max_len))

        if len(snippets_list) == max_snippets:
            break

    return snippets_list

def make_regex_snippets(
    units: list[str],
    compiled_re: re.Pattern,
    *,
    max_snippets: int = 3,
    max_len: int = 180,
    context_before: int = 1,
    context_after: int = 1
) -> list[str]:
    snippets_list = []

    matching_units_indexes = _find_matching_unit_indexes(units=units, mode="regex",
                                                         compiled_re=compiled_re)

    windows_ranges_list = _build_context_windows(match_indexes=matching_units_indexes,
                                                 total_units=len(units),
                                                 before=context_before, after=context_after)

    for start, end in windows_ranges_list:
        snippets_list.append(_format_snippet_block(units=units,
                                                   start=start, end=end,
                                                   max_len=max_len))

        if len(snippets_list) == max_snippets:
            break

    return snippets_list