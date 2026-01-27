import hashlib
import re
import subprocess
from datetime import datetime
from typing import Literal
from pathlib import Path

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import QMainWindow, QLabel, QLineEdit, QPushButton, QProgressBar, QListWidget, QPlainTextEdit, \
    QVBoxLayout, QHBoxLayout, QWidget, QSplitter, QFileDialog, QRadioButton, QTextEdit, QListWidgetItem, \
    QAbstractItemView, QSizePolicy, QCheckBox
from PyQt6.QtGui import QColor, QTextCursor, QTextCharFormat, QTextDocument, QPixmap, QIcon, QFont

from core import query, persist
from core.models import FileRecord, Hit, SearchResult
from ui.worker import IndexWorker

# File extensions the UI allows the user to index/search.
EXTENSIONS = [".txt", ".log", ".py", ".md", ".csv", ".json", ".xml"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("File Search Engine")
        self.resize(900, 650)

        # Keep references to avoid garbage-collection while the background thread is running.
        # (If Python GC collects these, the worker/thread may stop unexpectedly.)
        self.thread: QThread | None = None
        self.worker: IndexWorker | None = None

        # Data produced by indexing (None until "Build Index" finishes successfully).
        # - files: list of scanned files with metadata (path/size/mtime/type)
        # - index: inverted index token -> list[Hit]
        self.files_by_id: dict[int, FileRecord] | None = None
        self.id_by_path: dict[str, int] | None = None
        self.index: dict[str, list[Hit]] | None = None
        self.casefold_index: dict[str, list[Hit]] | None = None
        self.unit_store: dict[int, list[str]] | None = None

        """
        Metadata describing the currently loaded/built index.

        This dictionary is meant to be saved alongside the index so that it can be
        validated, displayed to the user, and used to reproduce the same search
        behavior after loading.

        Typical keys (your current format):
          - "index_format_version": str
                Version of the on-disk index format (so you can change schema later).
          - "created_at": str
                ISO timestamp of when the index was created.
          - "indexed_root_dir": str
                The folder that was indexed (the root directory).
          - "extensions": list[str]
                Which file extensions were included in the scan (e.g., [".txt", ".py"]).
          - "tokenizer_config": dict
                Tokenization/search rules used to build the index, e.g.:
                    {
                      "min_length": int,
                      "stopwords_mode": str,
                      "keep_numbers": bool
                    }

        Note:
        - UI uses this to pass correct config into persist.save_index(...)
        - persist.load_index(...) returns this meta so the UI can show details
          and warn when the index might be outdated.
        """
        self.index_meta: dict | None = None

        # Last displayed results list (used to map a selected UI row -> SearchResult).
        self.last_results: list[SearchResult] = []
        self.last_query_tokens: list[str] = []
        self.last_search_mode: Literal["and", "contains", "exact", "regex"] = "and"

        self._build_ui()
        self._apply_style()
        self._connect_signals()

    # Create widgets and layouts (clean layout).
    def _build_ui(self) -> None:
        # --- Widget Initialization ---
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")

        self.status_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.path_edit = QLineEdit()
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("Search...")
        self.path_edit.setReadOnly(True)

        self.token_and_radio_button = QRadioButton("Token AND")
        self.token_contains_radio_button = QRadioButton("Token CONTAINS")
        self.exact_radio_button = QRadioButton("Exact")
        self.regex_radio_button = QRadioButton("Regex")

        self.case_sensitive_checkbox = QCheckBox("Case Sensitive")
        self.case_sensitive_checkbox.setChecked(False)

        self.browse_btn = QPushButton("Browse...")
        self.build_btn = QPushButton("Build Index")
        self.save_btn = QPushButton("Save Index")
        self.load_btn = QPushButton("Load Index")
        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("searchButton")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()

        self.results_list = QListWidget()
        self.snippets_box = QPlainTextEdit()
        self.snippets_box.setReadOnly(True)

        self.legend_list = QListWidget()
        self.legend_list.setMinimumWidth(180)
        self.legend_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        # --- Layout Construction ---
        main_layout = QVBoxLayout()
        main_widget = QWidget()

        # 1. Folder Row
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Folder:"))
        folder_layout.addWidget(self.path_edit)
        folder_layout.addWidget(self.browse_btn)

        # 2. Build & Status Row
        build_layout = QHBoxLayout()
        build_layout.addWidget(self.build_btn)
        build_layout.addWidget(self.save_btn)
        build_layout.addWidget(self.load_btn)
        build_layout.addWidget(self.progress)
        build_layout.addStretch(1)  # Elastic spacer pushes status_label to the right
        build_layout.addWidget(self.status_label)

        # 3. Search Row
        search_layout = QHBoxLayout()
        search_layout.addWidget(self.query_edit)
        search_layout.addWidget(self.search_btn)
        search_layout.addWidget(self.token_and_radio_button)
        search_layout.addWidget(self.token_contains_radio_button)
        search_layout.addWidget(self.exact_radio_button)
        search_layout.addWidget(self.regex_radio_button)
        search_layout.addWidget(self.case_sensitive_checkbox)

        # 4. Main Content Splitters
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Vertical split: Results (top) vs Snippets (bottom)
        results_snippets_splitter = QSplitter(Qt.Orientation.Vertical)
        results_snippets_splitter.addWidget(self.results_list)
        results_snippets_splitter.addWidget(self.snippets_box)
        results_snippets_splitter.setStretchFactor(0, 2)
        results_snippets_splitter.setStretchFactor(1, 3)

        self.main_splitter.addWidget(results_snippets_splitter)
        self.main_splitter.addWidget(self.legend_list)
        self.main_splitter.setSizes([600, 200])

        main_layout.addLayout(folder_layout)
        main_layout.addLayout(build_layout)
        main_layout.addLayout(search_layout)
        main_layout.addWidget(self.main_splitter)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            /* Base Theme - Slate 900 */
            QWidget {
                background: #0f172a; 
                color: #f8fafc;
                font-family: 'Segoe UI', 'Inter', system-ui, sans-serif;
                font-size: 13px;
            }

            /* Status Pill - Refined Glow */
            QLabel#statusLabel {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 4px 14px;
                color: #38bdf8;
                font-weight: 600;
                font-size: 11px;
                text-transform: uppercase;
            }

            /* Input & Output Fields - Deep Navy */
            QLineEdit, QListWidget, QPlainTextEdit {
                background: #020617;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #2563eb;
                line-height: 1.5;
            }
            QLineEdit:focus { 
                border: 1px solid #3b82f6; 
                background: #0f172a;
                transition: border-color 0.2s;
            }

            /* List Items Selection */
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #1e293b;
            }
            QListWidget::item:selected {
                background: #1d4ed8;
                color: white;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: #1e293b;
            }

            /* Modern Custom Scrollbars */
            QScrollBar:vertical {
                background: #0f172a; width: 10px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #334155; border-radius: 5px; min-height: 20px; margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #475569;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

            /* Standard Buttons */
            QPushButton {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 500;
                min-height: 24px;
            }
            QPushButton:hover {
                background: #334155;
                border-color: #475569;
            }
            QPushButton:pressed {
                background: #0f172a;
            }

            /* Action-Specific Button: Search */
            QPushButton#searchButton {
                background: #2563eb;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 20px;
            }
            QPushButton#searchButton:hover {
                background: #3b82f6;
            }
            QPushButton#searchButton:pressed {
                background: #1e40af;
            }

            /* Radio Buttons & Checkboxes */
            QRadioButton, QCheckBox {
                spacing: 8px;
            }
            QRadioButton::indicator, QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }

            /* Progress Bar */
            QProgressBar {
                border: 1px solid #1e293b;
                border-radius: 4px;
                text-align: center;
                background: #020617;
                height: 12px;
            }
            QProgressBar::chunk {
                background: #3b82f6;
                border-radius: 3px;
            }

            /* Splitter Handle */
            QSplitter::handle {
                background: #1e293b;
            }
            QSplitter::handle:horizontal { width: 2px; }
            QSplitter::handle:vertical { height: 2px; }
        """)

    # Connect buttons and worker signals
    def _connect_signals(self) -> None:
        # UI actions
        self.browse_btn.clicked.connect(self.on_browse_clicked)
        self.build_btn.clicked.connect(self.on_build_index_clicked)
        self.save_btn.clicked.connect(self.on_save_index_clicked)
        self.load_btn.clicked.connect(self.on_load_index_clicked)
        self.search_btn.clicked.connect(self.on_search_clicked)
        self.query_edit.returnPressed.connect(self.search_btn.click)

        # Selection/search UX
        self.results_list.itemSelectionChanged.connect(self.on_result_selected)
        self.query_edit.returnPressed.connect(self.on_search_clicked)

        self.results_list.itemDoubleClicked.connect(self.on_result_double_clicked)

    def on_browse_clicked(self) -> None:
        # Let user choose the folder to scan/index.
        explorer_dialog = QFileDialog()
        explorer_dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog_success = explorer_dialog.exec()

        if dialog_success:
            if len(explorer_dialog.selectedFiles()) > 0:
                # Choosing a new folder invalidates the previous index/results.
                self.path_edit.setText(explorer_dialog.selectedFiles()[0])
                self.files_by_id = None
                self.index = None
                self.last_results = []
                self.index_meta = None
                self.results_list.clear()
                self.snippets_box.clear()
                self.search_btn.setEnabled(False)
                self.save_btn.setEnabled(False)

    def on_build_index_clicked(self) -> None:
        # Start indexing in a background thread.
        if len(self.path_edit.text()) == 0:
            self.status_label.setText("No folder...")
            return

        # Disable controls while indexing is running (prevents re-entrance / double-start).
        self.browse_btn.setEnabled(False)
        self.build_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.search_btn.setEnabled(False)

        # Reset output UI.
        self.snippets_box.clear()
        self.progress.show()
        self.progress.setRange(0, 0)  # Busy/indeterminate mode while background work runs.
        self.progress.setFormat("Working...")
        self.status_label.setText("Starting...")

        # Create worker + thread. Worker does the heavy lifting; UI stays responsive.
        self.thread = QThread()
        self.worker = IndexWorker(self.path_edit.text(), EXTENSIONS)

        # Run the worker in a background thread; communicate back via signals.
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)

        # Worker -> UI communication (always happens on the main thread).
        self.worker.status.connect(self.on_index_status)
        self.worker.error.connect(self.on_index_error)
        self.worker.finished.connect(self.on_index_finished)

        # Always stop and clean up the thread when work ends (success or error).
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def on_save_index_clicked(self) -> None:
        # Save the current index to disk (meta.json + index files).
        if self.index is None or self.files_by_id is None:
            self.status_label.setText("No index to save")
            return

        explorer_dialog = QFileDialog()
        explorer_dialog.setFileMode(QFileDialog.FileMode.Directory)
        explorer_dialog.setWindowTitle("Select folder to save")
        dialog_success = explorer_dialog.exec()

        if dialog_success:
            try:
                if len(explorer_dialog.selectedFiles()) > 0:
                    if not Path(explorer_dialog.selectedFiles()[0]).is_dir():
                        raise NotADirectoryError("This path is not a directory path")

                    persist.save_index(
                        files_by_id=self.files_by_id,
                        id_by_path=self.id_by_path,
                        index=self.index,
                        out_dir=explorer_dialog.selectedFiles()[0],
                        meta=self.index_meta,
                    )
            except Exception as e:
                self.status_label.setText(f"Save failed, error: {e}")
            else:
                self.status_label.setText(f"Save index to: {explorer_dialog.selectedFiles()[0]} ")

    def on_load_index_clicked(self) -> None:
        # Load an index from disk (and enable searching immediately).
        explorer_dialog = QFileDialog()
        explorer_dialog.setFileMode(QFileDialog.FileMode.Directory)
        explorer_dialog.setWindowTitle("Select folder to index")
        dialog_success = explorer_dialog.exec()

        if dialog_success:
            if len(explorer_dialog.selectedFiles()) > 0:
                files_by_id, ids_by_path, index, meta = persist.load_index(explorer_dialog.selectedFiles()[0])

                # Replace current in-memory index with the loaded one.
                self.files_by_id = files_by_id
                self.id_by_path = ids_by_path
                self.index = index
                self.index_meta = meta

                self.search_btn.setEnabled(True)
                self.save_btn.setEnabled(True)
                self.snippets_box.clear()

                # Validate (basic safety check) and warn if something looks outdated.
                is_valid, problems = persist.validate_index(files_by_id=self.files_by_id)
                if not is_valid:
                    self.status_label.setText("Index may be outdated")
                else:
                    self.status_label.setText(
                        f"The system scanned {len(files_by_id)} files and {len(index.keys())} tokens"
                    )

    def on_index_status(self, message: str) -> None:
        # Live status messages from the background worker.
        self.status_label.setText(message)

    def on_index_error(self, message: str) -> None:
        # Worker failed: restore UI so the user can try again.
        self.status_label.setText(message)

        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.hide()

        self.browse_btn.setEnabled(True)
        self.build_btn.setEnabled(True)

    def on_index_finished(self, files: dict[int, FileRecord],
                          id_by_path: dict[str, int],
                          index: dict[str, list[Hit]],
                          casefold_index: dict[str, list[Hit]],
                          unit_store: dict[int, list[str]]) -> None:
        # Worker finished successfully: store index and enable Save/Search.
        self.files_by_id = files
        self.id_by_path = id_by_path
        self.index = index
        self.casefold_index = casefold_index
        self.unit_store = unit_store

        # Restore UI to "ready" state.
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.hide()

        self.browse_btn.setEnabled(True)
        self.build_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.search_btn.setEnabled(True)

        self.snippets_box.clear()
        self.status_label.setText(f"The system scanned {len(files)} files and {len(index.keys())} tokens")

        # Build meta that describes how this index was created.
        # This is saved/loaded with the index to preserve reproducibility and validation.
        self.index_meta = {
            "index_format_version": "1",
            "created_at": datetime.now().isoformat(),
            "indexed_root_dir": self.path_edit.text(),
            "extensions": EXTENSIONS,
            "tokenizer_config": {
                "min_length": 2,
                "stopwords_mode": "none",
                "keep_numbers": True,
            },
        }

    def on_search_clicked(self) -> None:
        if self.query_edit.text() == "":
            self.status_label.setText("Enter a query")
            return

        is_case_sensitive = False
        if self.case_sensitive_checkbox.isChecked():
            is_case_sensitive = True

        if not self.token_and_radio_button.isChecked() and not self.exact_radio_button.isChecked() \
                and not self.token_contains_radio_button.isChecked() \
                and not self.regex_radio_button.isChecked():
            self.token_and_radio_button.setChecked(True)

        if self.token_and_radio_button.isChecked():
            # Execute query against the in-memory index and display ranked results.
            if self.files_by_id is None or self.index is None:
                self.status_label.setText("Build index first")
                return

            self.last_query_tokens = query.tokenize_query(self.query_edit.text(),
                                                          case_sensitive=is_case_sensitive)
            self.update_token_legend(self.last_query_tokens)
            self.last_results = query.search_and(self.query_edit.text(), unit_store=self.unit_store,
                                                 files=self.files_by_id, index=self.index,
                                                 casefold_index=self.casefold_index,
                                                 case_sensitive=is_case_sensitive)
            self.last_search_mode = "and"
        elif self.token_contains_radio_button.isChecked():
            if self.files_by_id is None:
                self.status_label.setText("Select folder first")
                return

            self.last_query_tokens = query.tokenize_query(self.query_edit.text(),
                                                          case_sensitive=self.case_sensitive_checkbox.isChecked())
            self.update_token_legend(self.last_query_tokens)
            self.last_results = query.search_token_contains(self.query_edit.text(),
                                                            unit_store=self.unit_store,
                                                            files=self.files_by_id,
                                                            case_sensitive=is_case_sensitive)
            self.last_search_mode = "contains"
        elif self.exact_radio_button.isChecked():
            if self.files is None:
                self.status_label.setText("Select folder first")
                return

            self.last_results = query.search_exact(self.query_edit.text(),
                                                   unit_store=self.unit_store,
                                                   files=self.files_by_id,
                                                   case_sensitive=is_case_sensitive)
            self.legend_list.clear()
            self.last_query_tokens.clear()
            self.last_search_mode = "exact"
        elif self.regex_radio_button.isChecked():
            if self.files_by_id is None:
                self.status_label.setText("Select folder first")
                return

            try:
                self.last_results = query.search_regex(
                    self.query_edit.text(),
                    unit_store=self.unit_store,
                    files=self.files_by_id,
                    case_sensitive=is_case_sensitive
                )
            except ValueError:
                # Update UI to show the error and stop execution
                self.status_label.setText("Invalid regex")
                self.results_list.clear()
                return

            self.legend_list.clear()
            self.last_search_mode = "regex"
            self.last_query_tokens.clear()

        self.results_list.clear()

        if len(self.last_results) == 0:
            self.status_label.setText("No results")
            return

        self.status_label.setText("Results:")
        for result in self.last_results:
            self.results_list.addItem(f"score: {result.score} | matches: {result.matches_count} | path: {result.path}")

    """
    Read the selected event, get corresponding SearchResult,
    show snippets in the text box.
    """
    def on_result_selected(self) -> None:
        selected_items = self.results_list.selectedItems()

        if len(selected_items) == 0:
            self.status_label.setText("No result chosen")
            self.snippets_box.clear()
            return

        if len(selected_items) > 1:
            self.status_label.setText("More than one result chosen")
            return

        # currentRow() maps directly to self.last_results because items are added in the same order.
        row = self.results_list.currentRow()

        if row < 0 or row >= len(self.last_results):
            self.status_label.setText("Invalid selection")
            return

        # Show snippets for the selected result.
        self.snippets_box.setPlainText("\n".join(self.last_results[row].snippets))

        if self.last_search_mode == "exact":
            self.show_exact_snippets_with_highlight(self.last_results[row].snippets, self.query_edit.text(),
                                                    case_sensitive=self.case_sensitive_checkbox.isChecked())
        elif self.last_search_mode == "regex":
            self.show_regex_snippets_with_highlight(self.last_results[row].snippets, self.query_edit.text(),
                                                    case_sensitive=self.case_sensitive_checkbox.isChecked())
        else:
            self.show_token_snippets_with_highlight(self.last_results[row].snippets, self.last_query_tokens,
                                                    case_sensitive=self.case_sensitive_checkbox.isChecked())
        self.status_label.setText(f"Showing result for: {self.last_results[row].path}")

    """
        Render snippets into the QPlainTextEdit and highlight the exact
        (case-sensitive) query_text with yellow background.
    """
    def show_exact_snippets_with_highlight(
        self,
        snippets: list[str],
        query_text: str,
        case_sensitive: bool = False
    ) -> None:
        self.snippets_box.clear()
        self.snippets_box.setExtraSelections([])

        if not snippets:
            return

        query_text = query_text.strip()
        if not query_text:
            # Show text without highlights
            self.snippets_box.setPlainText("\n".join(snippets))
            return

        self.snippets_box.setPlainText("\n".join(snippets))

        fmt = QTextCharFormat()
        fmt.setBackground(QColor("yellow"))
        fmt.setForeground(QColor("Black"))

        selections: list[QTextEdit.ExtraSelection] = []
        doc: QTextDocument = self.snippets_box.document()
        allowed_ranges = self._compute_allowed_content_ranges()

        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        flags = QTextDocument.FindFlag.FindCaseSensitively if case_sensitive else QTextDocument.FindFlag(0)

        while True:
            cursor = doc.find(query_text, cursor, flags)
            if cursor.isNull():
                break

            start_pos = cursor.selectionStart()
            end_pos = cursor.selectionEnd()

            if not self._is_range_allowed(start_pos, end_pos, allowed_ranges):
                cursor.setPosition(cursor.selectionEnd())
                continue

            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            selections.append(sel)

            cursor.setPosition(cursor.selectionEnd())

        header_selections = self._style_snippet_headers()
        all_selections = selections + header_selections

        self.snippets_box.setExtraSelections(all_selections)

    def show_regex_snippets_with_highlight(self, snippets: list[str], pattern: str, *,
                                           case_sensitive: bool = False) -> None:
        self.snippets_box.clear()
        self.snippets_box.setExtraSelections([])

        if not snippets:
            return

        full_text = "\n".join(snippets)

        if not pattern:
            # Show text without highlights
            self.snippets_box.setPlainText("\n".join(snippets))
            return

        self.snippets_box.setPlainText("\n".join(snippets))

        # 1. Prepare the Regex
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled_re = re.compile(pattern, flags)
        except re.error:
            # If the user enters an invalid regex, we just don't highlight
            self.status_label.setText("Invalid regex")
            return

        fmt = QTextCharFormat()
        fmt.setBackground(QColor("yellow"))
        fmt.setForeground(QColor("Black"))

        selections: list[QTextEdit.ExtraSelection] = []
        doc: QTextDocument = self.snippets_box.document()
        allowed_ranges = self._compute_allowed_content_ranges()

        for match in compiled_re.finditer(full_text):
            start, end = match.span()

            cursor = QTextCursor(doc)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

            if not self._is_range_allowed(start,
                                   end,
                                   allowed_ranges):
                continue

            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            selections.append(sel)

        header_selections = self._style_snippet_headers()
        all_selections = selections + header_selections

        self.snippets_box.setExtraSelections(all_selections)

    """
        Return a stable background color for this token (same token -> same color).
        We hash the token and map it into HSV hue range, with fixed saturation/value.
    """
    @staticmethod
    def _color_for_token(token: str) -> QColor:
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        hue = digest[0]  # 0..255
        hue = int(hue * 360 / 256)

        color = QColor()
        color.setHsv(hue, 180, 255)
        return color

    @staticmethod
    def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
        for position in occupied:
            if start < position[1] and end > position[0]:
                return True

        return False

    """
        Render snippets into the QPlainTextEdit and highlight each token
        (case-insensitive OR case-sensitive depending on your tokenizer/search rules).
    """
    def show_token_snippets_with_highlight(
        self,
        snippets: list[str],
        tokens: list[str],
        case_sensitive: bool = False
    ) -> None:
        self.snippets_box.clear()
        self.snippets_box.setExtraSelections([])

        if not snippets:
            return

        tokens = set(tokens)
        tokens = sorted(list(tokens), key=lambda item: (-len(item), item))

        if len(tokens) == 0:
            # Show text without highlights
            self.snippets_box.setPlainText("\n".join(snippets))
            return

        self.snippets_box.setPlainText("\n".join(snippets))

        selections: list[QTextEdit.ExtraSelection] = []
        doc: QTextDocument = self.snippets_box.document()
        allowed_ranges = self._compute_allowed_content_ranges()

        flags = QTextDocument.FindFlag.FindCaseSensitively if case_sensitive else QTextDocument.FindFlag(0)

        occupied: list[tuple[int, int]] = []
        for token in tokens:
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.MoveOperation.Start)

            fmt = QTextCharFormat()
            fmt.setForeground(QColor("Black"))
            fmt.setBackground(self._color_for_token(token))

            while True:
                cursor = doc.find(token, cursor, flags)
                if cursor.isNull():
                    break

                start_position = cursor.selectionStart()
                end_position = cursor.selectionEnd()

                if self._overlaps(start_position, end_position, occupied) \
                        or not self._is_range_allowed(start_position,
                                                      end_position,
                                                      allowed_ranges):
                    cursor.setPosition(cursor.selectionEnd())
                    continue

                occupied.append((start_position, end_position))

                sel = QTextEdit.ExtraSelection()
                sel.cursor = cursor
                sel.format = fmt
                selections.append(sel)

                cursor.setPosition(cursor.selectionEnd())

        header_selections = self._style_snippet_headers()
        all_selections = selections + header_selections

        self.snippets_box.setExtraSelections(all_selections)

    def update_token_legend(self, tokens: list[str]) -> None:
        self.legend_list.clear()
        unique_tokens = set(tokens)
        unique_tokens = sorted(unique_tokens, key=len, reverse=True)

        for token in unique_tokens:
            pixmap = QPixmap(12, 12)
            token_color: QColor = self._color_for_token(token)
            pixmap.fill(token_color)

            item = QListWidgetItem(token)
            item.setIcon(QIcon(pixmap))

            self.legend_list.addItem(item)

    def _style_snippet_headers(self) -> list[QTextEdit.ExtraSelection]:
        extra_selections = []
        doc: QTextDocument = self.snippets_box.document()
        block = doc.begin()

        highlight_format = QTextCharFormat()
        highlight_format.setForeground(QColor("#00FFFF"))
        highlight_format.setFontWeight(QFont.Weight.Bold)
        highlight_format.setBackground(QColor("#2A2A2A"))

        while block.isValid():
            text = block.text().strip()

            if text.startswith("Line"):
                selection = QTextEdit.ExtraSelection()
                selection.format = highlight_format

                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)

                selection.cursor = cursor
                extra_selections.append(selection)

            block = block.next()

        return extra_selections

    def _compute_allowed_content_ranges(self) -> list[tuple[int, int]]:
        doc: QTextDocument = self.snippets_box.document()
        allowed_ranges: list[tuple[int, int]] = []

        block = doc.firstBlock()
        this_range: list[int] = list()
        while block.isValid():
            line_text = block.text()

            if line_text.strip().startswith("Line"):
                block = block.next()
                continue
            elif set(line_text.strip()) == {'-'}:
                if len(this_range) == 2:
                    allowed_ranges.append((this_range[0], this_range[1]))
                    this_range = []
            else:
                if len(this_range) == 0:
                    this_range.append(block.position())
                    this_range.append(block.position() + block.length())
                else:
                    this_range[1] = block.position() + block.length()

            block = block.next()

        if len(this_range) == 2 and (this_range[0], this_range[1]) not in allowed_ranges:
            allowed_ranges.append((this_range[0], this_range[1]))

        return allowed_ranges

    @staticmethod
    def _is_range_allowed(start: int, end: int,
                          allowed: list[tuple[int, int]]) -> bool:
        for allowed_range in allowed:
            if start >= allowed_range[0] and end <= allowed_range[1]:
                return True

        return False

    @staticmethod
    def _open_file_with_default_app(path: str) -> None:
        subprocess.Popen(["notepad.exe", path])

    def on_result_double_clicked(self) -> None:
        row_selected = self.results_list.currentRow()

        if len(self.last_results) > row_selected >= 0:
            path = self.last_results[row_selected].path
            pathlib_path = Path(path).resolve()

            if not pathlib_path.exists():
                self.status_label.setText("File not exists")
                return

            if not pathlib_path.is_file():
                self.status_label.setText("The path you chose is not a file's path")
                return

            self._open_file_with_default_app(path)