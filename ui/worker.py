from PyQt6.QtCore import pyqtSignal, QObject

from core import engine, indexer, persist
from core.models import FileRecord, Hit

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
            files_by_id, id_by_path, unit_store,\
            index, casefold_index = engine.build_index_fresh(root_dir=self.root_dir,
                                                             extensions=self.extensions,
                                                             min_length=self.min_length,
                                                             stopwords=self.stopwords,
                                                             keep_numbers=self.keep_numbers)

        except Exception as e:
            self.error.emit(f"Indexing Error: {e}")
            return
        else:
            # 2. Emit all three parts to the MainWindow
            self.finished.emit(files_by_id, id_by_path, index, casefold_index, unit_store)


class PostLoadWorker(QObject):
    status = pyqtSignal(str)

    error = pyqtSignal(str)

    finished = pyqtSignal(dict, dict, tuple)

    def __init__(self,
                 *,
                 files_by_id: dict[int, FileRecord],
                 index: dict[str, list[Hit]],
                 case_sensitive: bool):
        super().__init__()

        self.files_by_id = files_by_id
        self.index = index
        self.case_sensitive = case_sensitive

    def run(self) -> None:
        try:
            self.status.emit("Validating index...")

            validation: tuple[bool, list[str]] = persist.validate_index(files_by_id=self.files_by_id)

            self.status.emit("Preparing snippets...")

            unit_store: dict[int, list[str]] = indexer.build_unit_store_incremental(
                                                              files_to_process=self.files_by_id,
                                                              case_sensitive=self.case_sensitive)

            self.status.emit("Optimizing search...")

            casefold_index: dict[str, list[Hit]] = indexer.build_casefold_index(index=self.index)

        except Exception as e:
            self.error.emit(f"Load preparation error: {e}")
            return
        else:
            self.finished.emit(unit_store, casefold_index, validation)