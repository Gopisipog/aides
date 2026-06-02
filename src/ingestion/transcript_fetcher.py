"""
YouTube transcript fetcher — fallback for DRM-protected videos.

When video/audio download fails due to DRM, age restriction, or
other blocks, this module fetches captions/subtitles directly
from YouTube's API without downloading any media.
"""

import re
import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
)
try:
    from youtube_transcript_api._errors import VideoUnavailable
except ImportError:
    # Older versions of youtube-transcript-api don't have VideoUnavailable
    VideoUnavailable = type("VideoUnavailable", (Exception,), {})


class TranscriptFetcher:
    """Fetches YouTube captions/subtitles via the transcript API.

    This is a fallback when direct video/audio download fails.
    It extracts text-only transcripts without any media download,
    making it suitable for DRM-protected, age-restricted, or
    otherwise blocked videos.

    Features:
    - Multi-language support (auto-fallback: English → any)
    - Timestamped segments (same format as Whisper output)
    - Metadata extraction (via yt-dlp fallback)
    - Works for: DRM, age-restricted, members-only, deleted (partial)
    """

    def __init__(self):
        self._last_fetched = None

    def get_transcript(
        self,
        video_id: str,
        languages: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch transcript for a YouTube video.

        Args:
            video_id: YouTube video ID (e.g., "dQw4w9WgXcQ").
            languages: Preferred language codes (default: ['en', 'en-US']).

        Returns:
            List of dicts with 'text', 'start', 'duration' keys, or
            raises an appropriate exception.

        Raises:
            TranscriptsDisabled: No captions available for this video.
            NoTranscriptFound: Captions exist but not in requested language.
            VideoUnavailable: Video is private/deleted.
        """
        if languages is None:
            languages = ["en", "en-US", "en-GB"]

        try:
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id, languages=languages
            )
            self._last_fetched = {
                "source": "youtube_transcript_api",
                "video_id": video_id,
                "languages": languages,
                "segments_count": len(transcript),
            }

            # Normalize to match Whisper format
            segments = []
            for i, seg in enumerate(transcript):
                segments.append({
                    "start": float(seg["start"]),
                    "end": float(seg["start"]) + float(seg.get("duration", 5.0)),
                    "text": seg["text"].strip(),
                    "transcript": seg["text"].strip(),
                    "visual_text": "",
                    "segment_id": f"{video_id}_transcript_{i:04d}",
                })

            return segments

        except TranscriptsDisabled:
            raise
        except NoTranscriptFound:
            # Try automatic translation from any available language
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                # Try to get manually created transcript, fallback to auto-generated
                for t in transcript_list:
                    if t.is_translatable:
                        translated = t.translate("en")
                        segments_raw = translated.fetch()
                        segments = []
                        for i, seg in enumerate(segments_raw):
                            segments.append({
                                "start": float(seg["start"]),
                                "end": float(seg["start"]) + float(seg.get("duration", 5.0)),
                                "text": seg["text"].strip(),
                                "transcript": seg["text"].strip(),
                                "visual_text": "",
                                "segment_id": f"{video_id}_translated_{i:04d}",
                            })
                        return segments
            except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
                pass
            raise

    def get_transcript_with_metadata(
        self,
        video_id: str,
        languages: Optional[List[str]] = None,
        metadata_source: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Get transcript + video metadata in one call.

        Args:
            video_id: YouTube video ID.
            languages: Preferred transcript languages.
            metadata_source: 'yt_dlp' or None (skip metadata).

        Returns:
            Tuple of (segments, metadata_dict).
        """
        segments = self.get_transcript(video_id, languages)

        metadata = {
            "video_id": video_id,
            "source": "transcript_api",
            "title": f"YouTube Video ({video_id})",
            "channel": "Unknown",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "duration_sec": 0,
        }

        # Try to get richer metadata via yt-dlp (no download)
        if metadata_source == "yt_dlp" or not segments:
            try:
                import yt_dlp

                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "extract_flat": True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(
                        f"https://youtube.com/watch?v={video_id}", download=False
                    )
                    metadata["title"] = info.get("title", metadata["title"])
                    metadata["channel"] = info.get("uploader", metadata["channel"])
                    metadata["thumbnail_url"] = info.get(
                        "thumbnail", metadata["thumbnail_url"]
                    )
                    metadata["duration_sec"] = info.get("duration", 0)
            except Exception:
                pass  # metadata fetch is best-effort

        if segments:
            metadata["duration_sec"] = max(
                s["end"] for s in segments
            )

        return segments, metadata

    def supports_video(self, video_id: str) -> bool:
        """Quick check if transcript is available for a video (no download)."""
        try:
            YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            return True
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
            return False
        except Exception:
            return False