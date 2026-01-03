from core import tokenizer

# Return up to max_snippets lines containing any query token.
def make_snippets(
    path: str,
    query_tokens: list[str],
    *,
    max_snippets: int = 25,
    max_len: int = 180,
    min_length: int = 2,
    stopwords: set[str] | None = None,
    keep_numbers: bool = True
) -> list[str]:
    lines_matched: list[str] = []
    query_tokens = set(query_tokens)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            all_line_tokens_list = tokenizer.tokenize_line(line, min_length=min_length,
                                                           stopwords=stopwords, keep_numbers=keep_numbers)
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
    max_len: int = 180
) -> list[str]:
    snippets_list: list[str] = list()

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if query_text in line:
                line = line.replace("\n", "")
                snippets_list.append(line[:max_len])
            if len(snippets_list) == max_snippets:
                break

    return snippets_list



