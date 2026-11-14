"""Safe filename sanitization, MIME/extension mapping, and collision resolution."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from link_downloader.core.enums import OverwriteBehavior
from link_downloader.core.exceptions import FileCollisionError, ValidationError

_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)

_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_MULTI_SPACE_RE = re.compile(r"\s+")
_CD_EXT_FILENAME_RE = re.compile(
    r"""filename\*\s*=\s*(?:UTF-8|utf-8)?''([^;\r\n"']+)""",
    re.IGNORECASE,
)
_CD_QUOTED_FILENAME_RE = re.compile(r'filename\s*=\s*"([^"\r\n]+)"', re.IGNORECASE)
_CD_PLAIN_FILENAME_RE = re.compile(r"filename\s*=\s*([^;\r\n\"']+)", re.IGNORECASE)

MIME_EXTENSION_MAP: dict[str, str] = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/mpeg": ".mpeg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/webm": ".weba",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/gzip": ".gz",
    "application/x-gzip": ".gz",
    "application/x-tar": ".tar",
    "application/x-7z-compressed": ".7z",
    "application/vnd.rar": ".rar",
    "application/x-rar-compressed": ".rar",
    "application/x-bzip2": ".bz2",
    "application/x-xz": ".xz",
    "application/vnd.debian.binary-package": ".deb",
    "application/x-debian-package": ".deb",
    "application/x-rpm": ".rpm",
    "application/x-apple-diskimage": ".dmg",
    "application/vnd.microsoft.portable-executable": ".exe",
    "application/x-msdownload": ".exe",
    "application/json": ".json",
    "text/plain": ".txt",
    "text/csv": ".csv",
}

DIRECT_FILE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
        ".avi",
        ".m4v",
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
        ".opus",
        ".wav",
        ".flac",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".svg",
        ".bmp",
        ".ico",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".txt",
        ".csv",
        ".md",
        ".json",
        ".xml",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".deb",
        ".rpm",
        ".appimage",
        ".dmg",
        ".pkg",
        ".exe",
        ".msi",
        ".iso",
        ".whl",
        ".apk",
    }
)

_VIDEO_EXTS = frozenset({".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".mpeg", ".mpg", ".flv"})
_AUDIO_EXTS = frozenset({".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".weba"})
_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp", ".ico", ".avif"})
_DOC_EXTS = frozenset(
    {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".md", ".rtf", ".odt"}
)
_ARCHIVE_EXTS = frozenset({".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".zst"})
_PKG_EXTS = frozenset({".deb", ".rpm", ".appimage", ".dmg", ".pkg", ".exe", ".msi", ".iso", ".whl", ".apk"})


def _extract_basename(raw_name: str) -> str:
    """Return the final path segment across both POSIX and Windows separators."""
    parts = re.split(r"[/\\]+", raw_name.strip())
    for segment in reversed(parts):
        if segment and segment not in {".", ".."}:
            return segment
    return ""


def sanitize_filename(name: str, *, default: str = "download", max_length: int = 200) -> str:
    """Sanitize a filename to prevent path traversal, invalid characters, and reserved names."""
    if not isinstance(name, str):
        return default

    candidate = _extract_basename(name)
    candidate = _INVALID_FILENAME_CHARS_RE.sub("_", candidate)
    candidate = candidate.replace("..", "_")
    candidate = _MULTI_SPACE_RE.sub(" ", candidate).strip(" .")

    if not candidate or candidate in {".", ".."}:
        candidate = default

    path_obj = Path(candidate)
    stem = path_obj.stem.strip(" .")
    suffix = path_obj.suffix.strip()

    if not stem:
        stem = default

    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"{stem}_"

    if len(stem) + len(suffix) > max_length:
        keep = max(1, max_length - len(suffix))
        stem = stem[:keep].rstrip(" .")
        if not stem:
            stem = default[:keep]

    result = f"{stem}{suffix}"
    return result or default


def detect_extension_from_mime(content_type: str | None) -> str | None:
    """Infer a safe lowercase file extension (with leading dot) from a Content-Type header."""
    if not content_type:
        return None
    mime = content_type.split(";", 1)[0].strip().lower()
    if not mime or mime == "application/octet-stream":
        return None
    if mime in MIME_EXTENSION_MAP:
        return MIME_EXTENSION_MAP[mime]
    guessed = mimetypes.guess_extension(mime)
    if guessed == ".jpe":
        return ".jpg"
    return guessed


def classify_file_category(ext: str | None, content_type: str | None = None) -> str:
    """Classify a direct download into a readable file category."""
    ext_low = (ext or "").lower()
    if ext_low in _VIDEO_EXTS:
        return "Video"
    if ext_low in _AUDIO_EXTS:
        return "Audio"
    if ext_low in _IMAGE_EXTS:
        return "Image"
    if ext_low in _DOC_EXTS:
        return "Document"
    if ext_low in _ARCHIVE_EXTS:
        return "Archive"
    if ext_low in _PKG_EXTS:
        return "Software Package"

    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime.startswith("video/"):
        return "Video"
    if mime.startswith("audio/"):
        return "Audio"
    if mime.startswith("image/"):
        return "Image"
    if mime == "application/pdf":
        return "Document"
    return "Data / File"


def parse_content_disposition(header_value: str | None) -> str | None:
    """Extract and sanitize a filename from an HTTP Content-Disposition header."""
    if not header_value:
        return None

    ext_match = _CD_EXT_FILENAME_RE.search(header_value)
    if ext_match:
        decoded = unquote(ext_match.group(1).strip())
        base = _extract_basename(decoded)
        if base:
            return sanitize_filename(base)

    quoted_match = _CD_QUOTED_FILENAME_RE.search(header_value)
    if quoted_match:
        decoded = unquote(quoted_match.group(1).strip())
        base = _extract_basename(decoded)
        if base:
            return sanitize_filename(base)

    plain_match = _CD_PLAIN_FILENAME_RE.search(header_value)
    if plain_match:
        decoded = unquote(plain_match.group(1).strip())
        base = _extract_basename(decoded)
        if base:
            return sanitize_filename(base)

    return None


def infer_filename_from_url(
    url: str,
    *,
    content_disposition: str | None = None,
    content_type: str | None = None,
    default_stem: str = "download",
) -> str:
    """Determine a safe filename using Content-Disposition, URL path, and MIME type."""
    from_cd = parse_content_disposition(content_disposition)
    if from_cd:
        if not Path(from_cd).suffix:
            ext = detect_extension_from_mime(content_type)
            if ext:
                return sanitize_filename(f"{from_cd}{ext}")
        return from_cd

    parsed = urlsplit(url)
    path_segment = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
    if path_segment:
        sanitized = sanitize_filename(path_segment, default=default_stem)
        if not Path(sanitized).suffix:
            ext = detect_extension_from_mime(content_type)
            if ext:
                return sanitize_filename(f"{sanitized}{ext}")
        return sanitized

    ext = detect_extension_from_mime(content_type) or ""
    host = sanitize_filename(parsed.hostname or default_stem, default=default_stem)
    return sanitize_filename(f"{host}{ext}", default=f"{default_stem}{ext}")


def resolve_collision_safe_path(
    directory: Path,
    filename: str,
    behavior: OverwriteBehavior = OverwriteBehavior.RENAME,
    reserved_paths: set[Path] | None = None,
) -> Path:
    """Resolve a destination path guaranteed to stay within directory and honor collision policy."""
    base_dir = Path(directory).expanduser().resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(filename)
    candidate = (base_dir / safe_name).resolve()
    if not candidate.is_relative_to(base_dir):
        raise ValidationError(f"Destination path '{candidate}' escapes download folder.")

    reserved_resolved = {p.resolve() for p in (reserved_paths or set())}

    def _is_taken(path: Path) -> bool:
        part_path = Path(f"{path}.part")
        return path.exists() or part_path.exists() or path in reserved_resolved

    if behavior == OverwriteBehavior.OVERWRITE:
        if candidate not in reserved_resolved:
            return candidate
    elif behavior == OverwriteBehavior.SKIP:
        if _is_taken(candidate):
            raise FileCollisionError(
                f"Skipped download because '{candidate.name}' already exists or is queued.",
            )
        return candidate

    if not _is_taken(candidate):
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while counter < 10_000:
        numbered_name = sanitize_filename(f"{stem} ({counter}){suffix}")
        numbered = (base_dir / numbered_name).resolve()
        if not numbered.is_relative_to(base_dir):
            raise ValidationError("Generated collision path escaped destination directory.")
        if not _is_taken(numbered):
            return numbered
        counter += 1

    raise FileCollisionError(f"Unable to find a unique filename for '{safe_name}'.")
