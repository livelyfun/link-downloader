"""Responsive & paginated SQLite download history page."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from link_downloader.core.enums import DownloadStatus
from link_downloader.core.models import HistoryEntry, format_bytes
from link_downloader.platform.file_actions import open_file, reveal_in_file_manager
from link_downloader.services.download_manager import DownloadManager
from link_downloader.ui.components.empty_state import EmptyStateWidget
from link_downloader.ui.components.pagination_bar import PaginationBar
from link_downloader.ui.styles.theme import make_icon


def _format_timestamp(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_str[:16]


class _HistoryRowCard(QFrame):
    open_clicked = Signal(str)
    folder_clicked = Signal(str)
    redownload_clicked = Signal(str)
    delete_clicked = Signal(str)

    def __init__(self, entry: HistoryEntry, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._entry = entry

        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(14, 10, 14, 10)
        self._box.setSpacing(10)

        info = QVBoxLayout()
        info.setSpacing(3)

        top_line = QHBoxLayout()
        top_line.setSpacing(6)
        title = QLabel(entry.title or entry.filename)
        title.setStyleSheet("font-size: 13px; font-weight: 600;")
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top_line.addWidget(title, 1)

        platform_pill = QLabel(entry.platform or "Unknown")
        platform_pill.setObjectName("BadgeInfo")
        top_line.addWidget(platform_pill)

        status_badge = QLabel(entry.status.title())
        badge_map = {
            DownloadStatus.COMPLETED.value: "BadgeSuccess",
            DownloadStatus.FAILED.value: "BadgeDanger",
            DownloadStatus.CANCELLED.value: "BadgeWarning",
        }
        status_badge.setObjectName(badge_map.get(entry.status, "BadgeInfo"))
        top_line.addWidget(status_badge)
        info.addLayout(top_line)

        meta_parts = [
            _format_timestamp(entry.completed_at or entry.started_at),
            entry.format_label or entry.format_id or "default",
            format_bytes(entry.file_size) if entry.file_size else None,
        ]
        meta_lbl = QLabel(" · ".join(p for p in meta_parts if p))
        meta_lbl.setObjectName("MutedLabel")
        meta_lbl.setWordWrap(True)
        meta_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(meta_lbl)

        if entry.file_path:
            path_lbl = QLabel(entry.file_path)
            path_lbl.setObjectName("MutedLabel")
            path_lbl.setWordWrap(True)
            path_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            info.addWidget(path_lbl)
        if entry.error_details:
            err_lbl = QLabel(entry.error_details)
            err_lbl.setObjectName("ErrorLabel")
            err_lbl.setWordWrap(True)
            err_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            info.addWidget(err_lbl)

        self._box.addLayout(info, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)

        file_exists = bool(entry.file_path and Path(entry.file_path).exists())
        if entry.status == DownloadStatus.COMPLETED.value:
            open_btn = QPushButton("Open")
            open_btn.setObjectName("GhostButton")
            open_btn.setEnabled(file_exists)
            open_btn.setToolTip("Open file" if file_exists else "File no longer exists at this path")
            open_btn.clicked.connect(lambda: self.open_clicked.emit(entry.file_path or ""))
            actions.addWidget(open_btn)

            folder_btn = QPushButton("Folder")
            folder_btn.setObjectName("GhostButton")
            folder_btn.setIcon(make_icon("folder", "#475569", 14))
            folder_btn.clicked.connect(lambda: self.folder_clicked.emit(entry.file_path or ""))
            actions.addWidget(folder_btn)

        again_btn = QPushButton("Download Again")
        again_btn.setObjectName("GhostButton")
        again_btn.setIcon(make_icon("retry", "#475569", 14))
        again_btn.clicked.connect(lambda: self.redownload_clicked.emit(entry.url))
        actions.addWidget(again_btn)

        del_btn = QPushButton()
        del_btn.setObjectName("GhostButton")
        del_btn.setIcon(make_icon("trash", "#dc2626", 14))
        del_btn.setToolTip("Remove from history")
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(entry.id))
        actions.addWidget(del_btn)
        actions.addStretch(0)

        self._box.addLayout(actions)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        direction = (
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 560
            else QBoxLayout.Direction.LeftToRight
        )
        if self._box.direction() != direction:
            self._box.setDirection(direction)


class HistoryPage(QWidget):
    """Displays persistent download history with search, filters, responsive cards, and pagination."""

    redownload_requested = Signal(str)

    def __init__(self, manager: DownloadManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top toolbar
        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        header = QHBoxLayout(toolbar)
        header.setContentsMargins(20, 10, 20, 10)
        header.setSpacing(8)
        title = QLabel("History")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("GhostButton")
        self.refresh_btn.setIcon(make_icon("retry", "#475569", 14))
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)

        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.setObjectName("DangerButton")
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        header.addWidget(self.clear_btn)
        root.addWidget(toolbar)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 14, 20, 14)
        body_lay.setSpacing(10)

        # Responsive filter bar
        self._filters_box = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._filters_box.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter history by title, filename, URL, or source...")
        self.search_input.setMinimumWidth(120)
        self.search_input.textChanged.connect(self._on_filter_changed)
        self._filters_box.addWidget(self.search_input, 1)

        combos_row = QHBoxLayout()
        combos_row.setSpacing(8)
        self.status_combo = QComboBox()
        self.status_combo.addItems(["All", "Completed", "Failed", "Cancelled"])
        self.status_combo.currentIndexChanged.connect(self._on_filter_changed)
        combos_row.addWidget(self.status_combo)

        self.platform_combo = QComboBox()
        self.platform_combo.addItem("All Sources")
        self.platform_combo.currentIndexChanged.connect(self._on_filter_changed)
        combos_row.addWidget(self.platform_combo)
        self._filters_box.addLayout(combos_row)
        body_lay.addLayout(self._filters_box)

        # Scroll list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body_lay.addWidget(scroll, 1)

        self._content = QWidget()
        self._content.setObjectName("ScrollContent")
        scroll.setWidget(self._content)

        self._list_layout = QVBoxLayout(self._content)
        self._list_layout.setContentsMargins(0, 0, 6, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.empty_state = EmptyStateWidget(
            "No Matching History",
            "Completed, failed, and cancelled downloads are stored locally in SQLite and appear here.",
            icon_name="history",
        )
        self._list_layout.addWidget(self.empty_state)

        self.pagination_bar = PaginationBar(
            default_page_size=10,
            page_size_options=(5, 10, 25, 50),
        )
        self.pagination_bar.page_changed.connect(lambda _p: self.refresh())
        self.pagination_bar.page_size_changed.connect(lambda _s: self.refresh())
        body_lay.addWidget(self.pagination_bar)

        root.addWidget(body, 1)

        self._manager.signals.history_updated.connect(self.refresh)
        self.refresh()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        direction = (
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 540
            else QBoxLayout.Direction.LeftToRight
        )
        if self._filters_box.direction() != direction:
            self._filters_box.setDirection(direction)

    def _on_filter_changed(self) -> None:
        self.pagination_bar.reset_page()
        self.refresh()

    def _refresh_platform_options(self) -> None:
        current = self.platform_combo.currentText()
        platforms = self._manager.history_repo.get_distinct_platforms()
        self.platform_combo.blockSignals(True)
        self.platform_combo.clear()
        self.platform_combo.addItem("All Sources")
        self.platform_combo.addItems(platforms)
        idx = self.platform_combo.findText(current)
        if idx >= 0:
            self.platform_combo.setCurrentIndex(idx)
        self.platform_combo.blockSignals(False)

    def refresh(self) -> None:
        self._refresh_platform_options()
        query = self.search_input.text().strip()
        status = self.status_combo.currentText()
        platform = self.platform_combo.currentText()
        if platform == "All Sources":
            platform = ""

        entries = self._manager.history_repo.list_entries(
            search_query=query,
            status_filter="" if status == "All" else status.lower(),
            platform_filter=platform,
        )

        self.pagination_bar.set_total_items(len(entries))
        paged_entries = self.pagination_bar.current_slice(entries)

        # Clear existing row cards while keeping empty_state
        for idx in reversed(range(self._list_layout.count())):
            item = self._list_layout.itemAt(idx)
            widget = item.widget()
            if widget is not None and widget is not self.empty_state:
                self._list_layout.removeWidget(widget)
                widget.deleteLater()

        for entry in paged_entries:
            card = _HistoryRowCard(entry)
            card.open_clicked.connect(open_file)
            card.folder_clicked.connect(
                lambda fp: reveal_in_file_manager(fp, self._manager.settings.download_folder)
            )
            card.redownload_clicked.connect(self.redownload_requested.emit)
            card.delete_clicked.connect(self._delete_entry)
            self._list_layout.addWidget(card)

        self.empty_state.setVisible(len(entries) == 0)
        self.clear_btn.setEnabled(len(entries) > 0 or bool(query or status != "All" or platform))

    def _delete_entry(self, entry_id: str) -> None:
        self._manager.history_repo.delete_entry(entry_id)
        self.refresh()

    def _on_clear_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear Download History",
            "Remove all entries from your local download history? Downloaded files on disk will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.history_repo.clear_history()
            self.pagination_bar.reset_page()
            self.refresh()
