import re

# Normalize text (lowercase, trim, basic cleanup)
def normalize_text(text: str, keep_numbers: bool, case_sensitive: bool) -> str:
    normalized_text = " ".join(re.split(r"[^a-zA-Z\d\s]", text))

    if not case_sensitive:
        normalized_text = normalized_text.casefold()

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
def tokenize_unit(unit: str, min_length: int = 2,
                  stopwords: set[str] | None = None, keep_numbers: bool = True,
                  case_sensitive: bool = False) -> list[str]:
    tokenized_list = split_to_tokens(normalize_text(unit, keep_numbers, case_sensitive=case_sensitive))
    tokenized_list = filter_tokens(tokenized_list, stopwords, min_length)

    return tokenized_list

