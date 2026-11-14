"""System diagnostics and dependency report dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from link_downloader.core.models import DependencyStatus, MigrationReport
from link_downloader.platform.paths import get_config_dir, get_data_dir, get_log_dir
from link_downloader.platform.system_integration import get_system_summary


class DiagnosticDialog(QDialog):
    """Displays cross-platform environment, path, migration, and dependency diagnostics."""

    def __init__(
        self,
        dependencies: list[DependencyStatus],
        migration_report: MigrationReport,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("System Diagnostics")
        self.resize(680, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QLabel("Environment & Dependency Diagnostics")
        header.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(header)

        summary = get_system_summary()
        lines = [
            f"Application: {summary.app_name} v{summary.app_version} (frozen={summary.is_frozen})",
            f"OS / Arch: {summary.os_name} {summary.os_release} ({summary.architecture})",
            f"Python: {summary.python_version}",
            f"Config Dir: {get_config_dir()}",
            f"Data Dir: {get_data_dir()}",
            f"Log Dir: {get_log_dir()}",
            f"Legacy Migration: config_migrated={migration_report.config_migrated}, "
            f"history_imported={migration_report.history_imported_count}, "
            f"history_skipped={migration_report.history_skipped_count}",
            "",
            "--- Dependencies ---",
        ]
        for dep in dependencies:
            status = "OK" if dep.available else "MISSING"
            lines.append(
                f"[{status}] ({dep.category.value.upper()}) {dep.name}"
                f" | version={dep.version or 'n/a'}"
                f" | path={dep.path or 'n/a'}"
            )
            if not dep.available:
                lines.append(f"    Impact: {dep.impact}")
                lines.append(f"    Install: {dep.install_hint}")
                lines.append(f"    Verify: {dep.verify_command}")

        self.text_area = QPlainTextEdit("\n".join(lines))
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self.text_area, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        copy_btn = QPushButton("Copy Report")
        copy_btn.setObjectName("GhostButton")
        copy_btn.clicked.connect(self._copy_report)
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("PrimaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _copy_report(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text_area.toPlainText())
