"""Platform integration layer exports."""

from link_downloader.platform.file_actions import open_file, open_folder, reveal_in_file_manager
from link_downloader.platform.paths import (
    get_app_icon_path,
    get_assets_dir,
    get_cache_dir,
    get_config_dir,
    get_data_dir,
    get_default_download_dir,
    get_legacy_config_dir,
    get_log_dir,
)
from link_downloader.platform.system_integration import (
    SystemSummary,
    get_platform_key,
    get_system_summary,
)

__all__ = [
    "SystemSummary",
    "get_app_icon_path",
    "get_assets_dir",
    "get_cache_dir",
    "get_config_dir",
    "get_data_dir",
    "get_default_download_dir",
    "get_legacy_config_dir",
    "get_log_dir",
    "get_platform_key",
    "get_system_summary",
    "open_file",
    "open_folder",
    "reveal_in_file_manager",
]
