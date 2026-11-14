"""Metadata resolution and safe remote thumbnail fetching."""

from __future__ import annotations

import logging

import httpx

from link_downloader.core.models import ResourceMetadata
from link_downloader.core.validators import normalize_and_validate_url, validate_redirect_url
from link_downloader.engines.resolver import UrlCapabilityResolver

logger = logging.getLogger(__name__)
MAX_THUMBNAIL_BYTES = 8 * 1024 * 1024  # 8 MiB safety cap


class MetadataService:
    """Coordinates URL resolution and safe bounded thumbnail downloading."""

    def __init__(
        self,
        resolver: UrlCapabilityResolver,
        *,
        allow_private: bool = False,
        prefer_ipv4: bool = True,
    ) -> None:
        self._resolver = resolver
        self._allow_private = allow_private
        self._prefer_ipv4 = prefer_ipv4

    def resolve(self, raw_url: str, *, allow_playlist: bool = False) -> ResourceMetadata:
        """Resolve a URL into normalized resource metadata."""
        return self._resolver.resolve(raw_url, allow_playlist=allow_playlist)

    def fetch_thumbnail_bytes(self, thumbnail_url: str | None) -> bytes | None:
        """Safely fetch thumbnail image bytes with size, timeout, and redirect limits."""
        if not thumbnail_url:
            return None
        try:
            current_url = normalize_and_validate_url(
                thumbnail_url,
                allow_private=self._allow_private,
                strict_dns=False,
            )
            transport = (
                httpx.HTTPTransport(local_address="0.0.0.0")
                if self._prefer_ipv4
                else httpx.HTTPTransport()
            )
            with httpx.Client(
                follow_redirects=False,
                timeout=httpx.Timeout(connect=6.0, read=10.0, write=6.0, pool=6.0),
                transport=transport,
                headers={"User-Agent": "LinkDownloader/2.0"},
            ) as client:
                for _ in range(5):
                    resp = client.get(current_url)
                    if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                        current_url = validate_redirect_url(
                            resp.headers["location"],
                            current_url,
                            allow_private=self._allow_private,
                            strict_dns=False,
                        )
                        continue
                    if resp.status_code != 200:
                        return None
                    content_type = resp.headers.get("content-type", "").lower()
                    if content_type and not content_type.startswith("image/"):
                        return None
                    data = resp.content
                    if not data or len(data) > MAX_THUMBNAIL_BYTES:
                        return None
                    return data
        except Exception:
            logger.debug("Thumbnail fetch failed for %s", thumbnail_url, exc_info=True)
        return None
