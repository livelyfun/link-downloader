"""Controlled yt-dlp and direct-file metadata fixtures for offline automated tests."""

from __future__ import annotations

SAMPLE_YOUTUBE_INFO: dict = {
    "id": "dQw4w9WgXcQ",
    "title": "Sample Cross-Platform Demo Video",
    "extractor": "youtube",
    "extractor_key": "Youtube",
    "uploader": "Demo Channel",
    "duration": 212,
    "view_count": 1_250_000,
    "upload_date": "20250501",
    "description": "A controlled test video metadata fixture.",
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    "formats": [
        {
            "format_id": "18",
            "ext": "mp4",
            "vcodec": "avc1.42001E",
            "acodec": "mp4a.40.2",
            "height": 360,
            "width": 640,
            "fps": 30,
            "filesize": 12_500_000,
            "tbr": 450.0,
        },
        {
            "format_id": "136",
            "ext": "mp4",
            "vcodec": "avc1.4d401f",
            "acodec": "none",
            "height": 720,
            "width": 1280,
            "fps": 30,
            "filesize": 28_000_000,
            "tbr": 1100.0,
        },
        {
            "format_id": "137",
            "ext": "mp4",
            "vcodec": "avc1.640028",
            "acodec": "none",
            "height": 1080,
            "width": 1920,
            "fps": 60,
            "filesize": 64_000_000,
            "tbr": 2400.0,
        },
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 128.0,
            "filesize": 3_400_000,
        },
    ],
}

SAMPLE_PLAYLIST_INFO: dict = {
    "_type": "playlist",
    "id": "PL12345",
    "title": "Sample Demo Playlist",
    "extractor": "youtube:tab",
    "extractor_key": "YoutubeTab",
    "playlist_count": 2,
    "entries": [
        {
            **SAMPLE_YOUTUBE_INFO,
            "id": "entry1",
            "title": "Playlist Item One",
        },
        {
            **SAMPLE_YOUTUBE_INFO,
            "id": "entry2",
            "title": "Playlist Item Two",
        },
    ],
}
