"""Reusable responsive neumorphic pagination bar for list and transfer views."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TypeVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

T = TypeVar("T")


class PaginationBar(QFrame):
    """Neumorphic pagination bar with page navigation, page size picker, and responsive layout."""

    page_changed = Signal(int)
    page_size_changed = Signal(int)

    def __init__(
        self,
        *,
        default_page_size: int = 10,
        page_size_options: tuple[int, ...] = (5, 10, 25, 50),
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SubCard")
        self._page_size_options = page_size_options
        self._page_size = default_page_size
        self._total_items = 0
        self._current_page = 1
        self._compact = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        self.info_label = QLabel("Showing 0 of 0")
        self.info_label.setObjectName("MutedLabel")
        layout.addWidget(self.info_label)

        self.page_size_combo = QComboBox()
        for opt in page_size_options:
            self.page_size_combo.addItem(f"{opt} / page", opt)
        idx = self.page_size_combo.findData(default_page_size)
        if idx >= 0:
            self.page_size_combo.setCurrentIndex(idx)
        self.page_size_combo.currentIndexChanged.connect(self._on_page_size_selected)
        layout.addWidget(self.page_size_combo)

        layout.addStretch()

        self.first_btn = QPushButton("<<")
        self.first_btn.setObjectName("GhostButton")
        self.first_btn.setToolTip("First page")
        self.first_btn.setFixedWidth(34)
        self.first_btn.clicked.connect(lambda: self.go_to_page(1))
        layout.addWidget(self.first_btn)

        self.prev_btn = QPushButton("< Prev")
        self.prev_btn.setObjectName("GhostButton")
        self.prev_btn.setToolTip("Previous page")
        self.prev_btn.clicked.connect(lambda: self.go_to_page(self._current_page - 1))
        layout.addWidget(self.prev_btn)

        self.page_label = QLabel("Page 1 of 1")
        self.page_label.setObjectName("BadgeInfo")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.page_label)

        self.next_btn = QPushButton("Next >")
        self.next_btn.setObjectName("GhostButton")
        self.next_btn.setToolTip("Next page")
        self.next_btn.clicked.connect(lambda: self.go_to_page(self._current_page + 1))
        layout.addWidget(self.next_btn)

        self.last_btn = QPushButton(">>")
        self.last_btn.setObjectName("GhostButton")
        self.last_btn.setToolTip("Last page")
        self.last_btn.setFixedWidth(32)
        self.last_btn.clicked.connect(lambda: self.go_to_page(self.total_pages))
        layout.addWidget(self.last_btn)

        self.setVisible(False)
        self._update_controls()

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def total_pages(self) -> int:
        if self._total_items <= 0:
            return 1
        return max(1, math.ceil(self._total_items / max(1, self._page_size)))

    def current_range(self, total: int | None = None) -> tuple[int, int]:
        """Return 0-based `[start, end)` indices for the active page."""
        count = self._total_items if total is None else total
        if count <= 0:
            return (0, 0)
        total_p = max(1, math.ceil(count / max(1, self._page_size)))
        page = max(1, min(self._current_page, total_p))
        start = (page - 1) * self._page_size
        end = min(count, start + self._page_size)
        return (start, end)

    def current_slice(self, items: Sequence[T]) -> list[T]:
        """Return items belonging to the active page."""
        start, end = self.current_range(len(items))
        return list(items[start:end])

    def set_total_items(self, total: int) -> None:
        self._total_items = max(0, total)
        if self._current_page > self.total_pages:
            self._current_page = self.total_pages
        elif self._current_page < 1:
            self._current_page = 1
        self.setVisible(self._total_items > 0)
        self._update_controls()

    def reset_page(self) -> None:
        self._current_page = 1
        self._update_controls()

    def go_to_page(self, page: int) -> None:
        clamped = max(1, min(page, self.total_pages))
        if clamped == self._current_page:
            return
        self._current_page = clamped
        self._update_controls()
        self.page_changed.emit(self._current_page)

    def _on_page_size_selected(self) -> None:
        new_size = int(self.page_size_combo.currentData() or self._page_size)
        if new_size == self._page_size:
            return
        self._page_size = new_size
        self._current_page = 1
        self._update_controls()
        self.page_size_changed.emit(self._page_size)

    def _update_controls(self) -> None:
        total_p = self.total_pages
        if self._total_items <= 0:
            self.info_label.setText("0 items")
        else:
            start, end = self.current_range(self._total_items)
            self.info_label.setText(f"Showing {start + 1}-{end} of {self._total_items}")

        if self._compact:
            self.page_label.setText(f"{self._current_page} / {total_p}")
        else:
            self.page_label.setText(f"Page {self._current_page} of {total_p}")

        has_prev = self._current_page > 1
        has_next = self._current_page < total_p
        self.first_btn.setEnabled(has_prev)
        self.prev_btn.setEnabled(has_prev)
        self.next_btn.setEnabled(has_next)
        self.last_btn.setEnabled(has_next)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 540
        if compact != self._compact:
            self._compact = compact
            self.info_label.setVisible(not compact)
            self.first_btn.setVisible(not compact)
            self.last_btn.setVisible(not compact)
            self._update_controls()
