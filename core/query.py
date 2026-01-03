from __future__ import annotations
import math
from core import tokenizer, snippets
from core.models import *

# Tokenize the user query using the same rules as the index
def tokenize_query(
    query: str,
    *,
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True
) -> list[str]:
    return tokenizer.tokenize_line(
        query,
        min_length=min_length,
        stopwords=stopwords,
        keep_numbers=keep_numbers,
    )

# AND search: return results for files that contain all query tokens.
def search_and(
    query: str,
    *,
    files: list[FileRecord],
    index: dict[str, list[Hit]],
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True,
    limit: int = 50
) -> list[SearchResult]:
    query_tokens = tokenize_query(
        query,
        min_length=min_length,
        stopwords=stopwords,
        keep_numbers=keep_numbers
    )

    # If no usable tokens, return empty
    if not query_tokens:
        return []

    # Build file-id sets per token (early exit if any token not in index)
    token_file_sets: list[set[int]] = []
    for tok in query_tokens:
        hits = index.get(tok)
        if not hits:
            return []  # AND: if one token missing, no results
        token_file_sets.append({h.file_id for h in hits})

    # AND = intersection
    common_file_ids = set.intersection(*token_file_sets)

    results: list[SearchResult] = []
    for file_id in list(common_file_ids):
        path = files[file_id].path

        # matches_count = total hits for those tokens in that file
        matches_count = 0
        for tok in query_tokens:
            lines_used: set[int] = set()
            for h in index[tok]:
                if h.file_id == file_id and h.line_no not in lines_used:
                    matches_count += 1
                    lines_used.add(h.line_no)

        score = _tfidf_score_for_file(file_id=file_id, query_tokens=query_tokens, index=index, total_docs=len(files))

        snippets_list = snippets.make_snippets(path, query_tokens, min_length=min_length,
                                               stopwords=stopwords, keep_numbers=keep_numbers)

        results.append(SearchResult(path=path, matches_count=matches_count, score=score, snippets=snippets_list))

    # sort best-first
    results.sort(key=lambda r: (-r.score, -r.matches_count, r.path))
    return results[:limit]

# Exact case-sensitive substring search across all files (no index needed)
def search_exact(
    query_text: str,
    *,
    files: list[FileRecord],
    limit: int = 50
) -> list[SearchResult]:
    if not query_text.strip():
        return []

    results_list: list[SearchResult] = list()

    for file_record in files:
        matches_count = _count_exact_in_file(file_record.path, query_text)

        # Skip files with zero matches (usually what you want in a search UI).
        if matches_count == 0:
            continue

        score = float(matches_count)

        results_list.append(SearchResult(path=file_record.path,
                                         matches_count=matches_count,
                                         score=score,
                                         snippets=snippets.make_exact_snippets(path=file_record.path,
                                                                               query_text=query_text)))

    results_list.sort(key=lambda r: (-r.matches_count, r.path))
    return results_list[:limit]

# Return number of lines in file that contain query_text (case-sensitive, count once per line)
def _count_exact_in_file(path: str, query_text: str) -> int:
    total_lines_matched = 0

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if query_text in line:
                total_lines_matched += 1

    return total_lines_matched

def _idf(token: str, *, index: dict[str, list[Hit]], total_docs: int) -> float:
    if token not in index:
        return 0.0

    unique_file_ids_for_token = {hit.file_id for hit in index[token]}
    df = len(unique_file_ids_for_token)

    return math.log((total_docs + 1) / (df + 1)) + 1

def _tf(token: str, file_id: int, *, index: dict[str, list[Hit]]) -> float:
    if token not in index:
        return 0.0

    all_file_token_hits = sum(1 for hit in index[token] if hit.file_id == file_id)
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
