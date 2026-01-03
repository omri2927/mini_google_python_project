import re

# Normalize text (lowercase, trim, basic cleanup)
def normalize_text(text: str, keep_numbers: bool) -> str:
    normalized_text = " ".join(re.split(r"[^a-zA-Z\d\s]", text)).lower()

    if not keep_numbers:
        normalized_text = re.sub(r'\d', ' ', normalized_text)

    return normalized_text

# Split normalized text into raw tokens.
def split_to_tokens(text: str) -> list[str]:
    return text.split()

# Remove unwanted tokens (too short, common word, etc.).
def filter_tokens(tokens: list[str], stopwords: set[str] | None, min_length: int) -> list[str]:
    stopwords = stopwords or set()
    filtered_tokens = []

    for tok in tokens:
        if len(tok) >= min_length and tok not in stopwords and tok not in filtered_tokens:
            filtered_tokens.append(tok)

    return filtered_tokens

# get a string representing a line from a file and splitting it to tokens
def tokenize_line(line: str, min_length: int = 2,
                  stopwords: set[str] | None = None, keep_numbers: bool = True) -> list[str]:
    tokenized_list = split_to_tokens(normalize_text(line, keep_numbers))
    tokenized_list = filter_tokens(tokenized_list, stopwords, min_length)

    return tokenized_list

