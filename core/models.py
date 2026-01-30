from enum import Enum
from typing import NamedTuple
from dataclasses import dataclass

class FileType(Enum):
    # Supported file types for filtering and classification
    TXT = 1
    LOG = 2
    PY = 3
    MD = 4
    CSV = 5
    JSON = 6
    XML = 7

class FileRecord(NamedTuple):
    # Metadata describing a single file discovered during scanning
    path: str
    size: int          # File size (e.g., in bytes)
    mtime: float       # Last modification time (Unix timestamp)
    filetype: FileType # File extension or logical type (could also be FileType)

class Hit(NamedTuple):
    # Represents a single match inside a file
    file_id: int
    unit_index: list[int]
    count: int

@dataclass
class SearchResult:
    # Aggregated search result per file
    path: str
    matches_count: int
    score: float
    snippets: list[str]  # Short context strings around each match
