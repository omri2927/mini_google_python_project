from PyQt6.QtCore import pyqtSignal, QObject
from core import indexer
from core.models import FileRecord

# Background worker responsible only for I/O-heavy and CPU-heavy indexing work.
# It runs in a QThread and communicates with the UI exclusively via signals.
class IndexWorker(QObject):
    # Emitted to report progress stages (e.g. "Scanning...", "Indexing...").
    status = pyqtSignal(str)

    # Emitted when an unrecoverable error occurs during scanning or indexing.
    error = pyqtSignal(str)

    # Emitted once on successful completion with the produced files and index.
    finished = pyqtSignal(dict, dict, dict, dict, dict) # files, id_by_path, main_index, casefold_index unit_store

    def __init__(self,
                 root_dir: str,
                 extensions: list[str],
                 *,
                 min_length: int = 2,
                 stopwords: set[str] | None = None,
                 keep_numbers: bool = True) -> None:
        super().__init__()
        # Configuration captured at creation time; not modified during execution.
        self.root_dir = root_dir
        self.extensions = set(extensions)
        self.min_length = min_length
        self.stopwords = stopwords
        self.keep_numbers = keep_numbers

    """
       Worker entry point executed inside a background thread.

       Flow:
       1) Emit status("Scanning...") and scan the filesystem.
       2) Emit status("Indexing...") and build the inverted index.
       3) Emit finished(files, index) on success.
       On any exception: emit error(...) and stop.
    """

    def run(self) -> None:
        try:
            self.status.emit("Scanning...")
            valid_files: list[FileRecord] = indexer.scan_files(
                self.root_dir, self.extensions
            )

            if not valid_files:
                self.error.emit("No files found matching the selected extensions.")
                return

            files_by_id = {i: f for i, f in enumerate(valid_files)}
            id_by_path = {f.path: i for i, f in files_by_id.items()}

            self.status.emit("Extracting text...")
            # Capture the unit_store, so we can show snippets later
            unit_store = indexer.build_unit_store_incremental(files_by_id, case_sensitive=False)

            self.status.emit("Building search index...")
            index = indexer.build_index(
                files_by_id,
                unit_store=unit_store,
                min_length=self.min_length,
                stopwords=self.stopwords,
                keep_numbers=self.keep_numbers
            )

            self.status.emit("Optimizing index for search...")
            casefold_index = indexer.build_casefold_index(index)

        except Exception as e:
            self.error.emit(f"Indexing Error: {e}")
            return
        else:
            # 2. Emit all three parts to the MainWindow
            self.finished.emit(files_by_id, id_by_path, index, casefold_index, unit_store)
