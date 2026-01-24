from __future__ import annotations
import math
import os
import re

from core import tokenizer, snippets, extractors
from core.models import *

# Tokenize the user query using the same rules as the index
def tokenize_query(
    query: str,
    *,
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    case_sensitive: bool = False
) -> list[str]:
    return tokenizer.tokenize_unit(
        query,
        min_length=min_length,
        stopwords=stopwords,
        keep_numbers=keep_numbers,
        case_sensitive=case_sensitive
    )

def build_casefold_index(index: dict[str, list[Hit]]) -> dict[str, list[Hit]]:
    ci: dict[str, list[Hit]] = dict()

    for token, hits in index.items():
        cf_token = token.casefold()

        if cf_token not in ci:
            ci[cf_token] = []

        ci[cf_token].extend(hits)

    return ci

# AND search: return results for files that contain all query tokens.
def search_and(
    query: str,
    *,
    unit_store: dict[int, list[str]],
    files: list[FileRecord],
    index: dict[str, list[Hit]],
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    limit: int = 50,
    case_sensitive: bool = False
) -> list[SearchResult]:
    query_tokens = tokenize_query(
        query,
        min_length=min_length,
        stopwords=stopwords,
        keep_numbers=keep_numbers,
        case_sensitive=case_sensitive
    )

    query_tokens = unique_preserve_order(query_tokens)

    # If no usable tokens, return empty
    if not query_tokens:
        return []

    # 1. Map each query token to its AGGREGATED hits (handling case variations)
    # This replaces the need for index[tok] later
    query_token_to_hits: dict[str, list[Hit]] = {}
    token_file_sets: list[set[int]] = []
    casefold_index = build_casefold_index(index=index)

    for tok in query_tokens:
        aggregated_hits = []
        if case_sensitive:
            aggregated_hits = index.get(tok, [])
        else:
            aggregated_hits = casefold_index.get(tok.casefold(), [])

        if not aggregated_hits:
            return []  # AND logic

        query_token_to_hits[tok] = aggregated_hits
        token_file_sets.append({h.file_id for h in aggregated_hits})

    common_file_ids = set.intersection(*token_file_sets)

    results: list[SearchResult] = []
    for file_id in common_file_ids:
        path = files[file_id].path

        # 2. Calculate matches_count using the aggregated hits we stored
        matches_count = 0
        units_used: set[int] = set()
        for tok in query_tokens:
            # USE query_token_to_hits instead of index[tok]
            for h in query_token_to_hits[tok]:
                if h.file_id == file_id and h.unit_index not in units_used:
                    matches_count += 1
                    units_used.add(h.unit_index)

        if case_sensitive:
            score = _tfidf_score_for_file(file_id=file_id, query_tokens=query_tokens,
                                          index=index, total_docs=len(files))
        else:
            score = _tfidf_score_for_file(file_id=file_id, query_tokens=query_tokens,
                                          index=query_token_to_hits, total_docs=len(files))
        snippets_list = snippets.make_snippets(unit_store[file_id], query_tokens, min_length=min_length,
                                               stopwords=stopwords, keep_numbers=keep_numbers,
                                               case_sensitive=case_sensitive)

        results.append(SearchResult(path=path, matches_count=matches_count, score=score, snippets=snippets_list))

    results.sort(key=lambda r: (-r.score, -r.matches_count, r.path))
    return results[:limit]

# Exact case-sensitive substring search across all files (no index needed)
def search_exact(
    query_text: str,
    *,
    unit_store: dict[int, list[str]],
    files: list[FileRecord],
    limit: int = 50,
    case_sensitive: bool = False
) -> list[SearchResult]:
    if not query_text.strip():
        return []

    results_list: list[SearchResult] = list()

    for file_id, file_record in enumerate(files):
        matches_count = _count_exact_in_file(unit_store[file_id], query_text, case_sensitive=case_sensitive)

        # Skip files with zero matches (usually what you want in a search UI).
        if matches_count == 0:
            continue

        score = float(matches_count)

        results_list.append(SearchResult(path=file_record.path,
                                         matches_count=matches_count,
                                         score=score,
                                         snippets=snippets.make_exact_snippets(unit_store[file_id],
                                                                               query_text=query_text,
                                                                               case_sensitive=case_sensitive)))

    results_list.sort(key=lambda r: (-r.matches_count, r.path))
    return results_list[:limit]

# Return number of lines in file that contain query_text (case-sensitive, count once per line)
def _count_exact_in_file(units: list[str],
                         query_text: str, case_sensitive: bool = False) -> int:
    total_units_matched = 0

    for unit in units:
        if case_sensitive:
            if query_text in unit:
                total_units_matched += 1
        else:
            if query_text.lower() in unit.lower():
                total_units_matched += 1

    return total_units_matched

def _idf(token: str, *, index: dict[str, list[Hit]], total_docs: int) -> float:
    if token not in index:
        return 0.0

    unique_file_ids_for_token = {hit.file_id for hit in index[token]}
    df = len(unique_file_ids_for_token)

    return math.log((total_docs + 1) / (df + 1)) + 1

def _tf(token: str, file_id: int, *, index: dict[str, list[Hit]]) -> float:
    if token not in index:
        return 0.0

    all_file_token_hits = sum(hit.count for hit in index[token] if hit.file_id == file_id)
    tf = math.sqrt(all_file_token_hits)

    return tf

def _tfidf_score_for_file(
    file_id: int,
    query_tokens: list[str],
    *,
    index: dict[str, list[Hit]],
    total_docs: int
) -> float:
    total_score = 0
    distinct_query_tokens = set(query_tokens)

    if len(distinct_query_tokens) == 0:
        return 0.0

    for token in distinct_query_tokens:
        tf = _tf(token, file_id, index=index)
        idf = _idf(token, index=index, total_docs=total_docs)

        total_score += tf * idf

    return total_score

def _unit_contains_any_token(unit: str, tokens: list[str], *, case_sensitive: bool) -> bool:
    for token in tokens:
        if not case_sensitive:
            if token.lower() in unit.lower():
                return True
        else:
            if token in unit:
                return True

    return False

def _count_units_with_any_token(units: list[str],
                                tokens: list[str], *, case_sensitive: bool) -> int:
    count_units_with_tokens = 0

    for unit in units:
        if _unit_contains_any_token(unit, tokens=tokens, case_sensitive=case_sensitive):
            count_units_with_tokens += 1

    return count_units_with_tokens

def unique_preserve_order(tokens: list[str]) -> list[str]:
    return list(dict.fromkeys(tokens))

def search_token_contains(
    query: str,
    *,
    unit_store: dict[int, list[str]],
    files: list[FileRecord],
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    limit: int = 50,
    case_sensitive: bool = False
) -> list[SearchResult]:
    query_tokens = tokenize_query(
        query,
        min_length=min_length,
        stopwords=stopwords,
        keep_numbers=keep_numbers,
        case_sensitive=case_sensitive
    )

    query_tokens = unique_preserve_order(query_tokens)

    # If no usable tokens, return empty
    if not query_tokens:
        return []

    results: list[SearchResult] = []
    for file_id, file in enumerate(files):
        file_matches = _count_units_with_any_token(unit_store[file_id], query_tokens, case_sensitive=case_sensitive)

        if file_matches == 0:
            continue

        file_score = float(file_matches)

        results.append(SearchResult(path=file.path, matches_count=file_matches,
                                    score=file_score,
                                    snippets=snippets.make_snippets_contains(unit_store[file_id],
                                                                             query_tokens=query_tokens,
                                                                             case_sensitive=case_sensitive)))

    results.sort(key=lambda r: (-r.score, -r.matches_count, r.path))
    return results[:limit]

def _count_regex_units_in_file(units: list[str], compiled_re: re.Pattern) -> int:
    count_units_matched = 0

    for unit in units:
        if compiled_re.search(unit):
            count_units_matched += 1

    return count_units_matched

def search_regex(pattern: str,
    *,
    unit_store: dict[int, list[str]],
    files: list[FileRecord],
    limit: int = 50,
    case_sensitive: bool = False
) -> list[SearchResult]:
    if not pattern.strip():
        return []

    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        compiled_re = re.compile(pattern, flags)
    except re.error:
        raise ValueError()

    results: list[SearchResult] = []
    for file_id, file in enumerate(files):
        file_matches = _count_regex_units_in_file(unit_store[file_id], compiled_re=compiled_re)

        if file_matches == 0:
            continue

        file_score = float(file_matches)

        results.append(SearchResult(path=file.path, matches_count=file_matches,
                                    score=file_score,
                                    snippets=snippets.make_regex_snippets(unit_store[file_id],
                                                                          compiled_re=compiled_re)))

    results.sort(key=lambda r: (-r.score, -r.matches_count, r.path))
    return results[:limit]

