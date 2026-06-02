"""
YouTube downloader with anti-bot protections.

Mimics a real browser to bypass YouTube's 403 Forbidden responses.
Uses multiple client types (android, web) as fallback strategies.
"""

import os
import yt_dlp


class YouTubeDownloader:
    """Wrapper for yt-dlp to download video and audio from YouTube URLs.

    Features:
    - Multiple client fallback strategies (android, web, mweb, tv)
    - Custom headers to mimic a real browser
    - Cookie-free extraction (no browser dependency)
    - Geo-bypass
    - Rate limiting avoidance
    """

    def __init__(self, output_dir="data/raw"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def _get_base_opts(self) -> dict:
        """Return base yt-dlp options that work around YouTube 403 errors."""
        return {
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "noprogress": True,
            "geo_bypass": True,
            "geo_bypass_country": "US",
            "geo_bypass_ipblock": True,
            # Mimic a modern Chrome browser
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
            },
            "extractor_args": {
                "youtube": {
                    "skip": ["webpage", "dash", "hls"],  # Skip problematic fetches
                    "player_client": ["android"],  # Android client less restricted
                }
            },
            # Avoid rate limiting
            "sleep_interval_requests": 1,
            "sleep_interval": 0.5,
            "max_sleep_interval": 2,
            # IPv4 fallback
            "source_address": "0.0.0.0",
        }

    def fetch_metadata(self, url: str) -> dict:
        """Fetches video title, channel, thumbnail and duration without downloading.

        Retries with different client types if 403 is encountered.
        """
        # First try: android client (most permissive)
        client_types = ["android", "web", "mweb", "tv"]
        last_error = None

        for client in client_types:
            try:
                opts = self._get_base_opts()
                opts["extractor_args"]["youtube"]["player_client"] = [client]
                opts["quiet"] = True
                opts["no_warnings"] = True
                opts["skip_download"] = True

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                return {
                    "video_id":      info.get("id", "unknown"),
                    "title":         info.get("title", "Unknown Title"),
                    "url":           url,
                    "thumbnail_url": info.get("thumbnail", ""),
                    "channel":       info.get("uploader", "Unknown"),
                    "duration_sec":  info.get("duration", 0),
                }
            except Exception as e:
                last_error = e
                # Only retry on 403 errors
                if "403" not in str(e):
                    break

        # All clients failed — raise the last error
        raise RuntimeError(
            f"Failed to fetch metadata for {url} after trying clients "
            f"{client_types}: {last_error}"
        )

    def _ffmpeg_dir(self):
        """Returns the directory containing the ffmpeg binary."""
        import shutil
        ffmpeg_bin = shutil.which("ffmpeg")
        return os.path.dirname(ffmpeg_bin) if ffmpeg_bin else None

    def _download(
        self,
        url: str,
        out_path: str,
        download_type: str = "audio",
        video_id: str = "audio",
    ) -> str:
        """Generic download method with format fallback chain.

        Tries multiple format strings and multiple client types to handle
        YouTube's ever-changing format availability.

        Args:
            url: YouTube URL.
            out_path: Path for the output file.
            download_type: 'audio' or 'video'.
            video_id: Identifier for logging.

        Returns:
            Path to the downloaded file.
        """
        # ── Format fallback chains ───────────────────────────────────────────
        if download_type == "video":
            format_fallbacks = [
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "bestvideo+bestaudio/best",
                "worstvideo+worstaudio/worst",  # fallback to lowest quality
            ]
        else:  # audio
            format_fallbacks = [
                "bestaudio[ext=m4a]/bestaudio",
                "bestaudio/best",
                "worstaudio/worst",
                "bestaudio[ext=webm]/bestaudio",  # some videos only have webm audio
            ]

        client_types = ["android", "web", "mweb", "tv"]
        last_error = None

        for client in client_types:
            for fmt in format_fallbacks:
                try:
                    opts = self._get_base_opts()
                    opts["extractor_args"]["youtube"]["player_client"] = [client]
                    opts["format"] = fmt
                    opts["outtmpl"] = out_path
                    opts["ffmpeg_location"] = self._ffmpeg_dir()
                    opts["overwrites"] = True
                    opts["noplaylist"] = True
                    opts["quiet"] = True
                    opts["no_warnings"] = True

                    if download_type == "audio":
                        opts["postprocessors"] = [
                            {
                                "key": "FFmpegExtractAudio",
                                "preferredcodec": "mp3",
                                "preferredquality": "192",
                            }
                        ]

                    # For video: disable postprocessing to avoid ffmpeg merge errors
                    # on poor quality videos
                    if download_type == "video":
                        opts["postprocessors"] = []

                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])

                    # Check for existence (audio may have .mp3 extension after pp)
                    actual_path = out_path
                    if download_type == "audio":
                        # After postprocessing, the .mp3 file may be at a different path
                        base_wo_ext = os.path.splitext(out_path)[0]
                        possible_paths = [
                            out_path,
                            base_wo_ext + ".mp3",
                            base_wo_ext + ".m4a",
                            base_wo_ext + ".webm",
                        ]
                        for p in possible_paths:
                            if os.path.exists(p):
                                actual_path = p
                                break

                    if os.path.exists(actual_path):
                        return actual_path

                    last_error = FileNotFoundError(
                        f"File not found after download: {out_path}"
                    )

                except Exception as e:
                    last_error = e
                    # If it's not a format/403 error, re-raise immediately
                    estr = str(e).lower()
                    if "403" not in estr and "format" not in estr and "requested" not in estr:
                        raise

        raise RuntimeError(
            f"Failed to download {download_type} from {url} after trying "
            f"{len(client_types)} clients × {len(format_fallbacks)} formats. "
            f"Last error: {last_error}"
        )

    def download_video(self, url: str, video_id: str = "video") -> str:
        """Downloads the video file for OCR processing."""
        filename = f"{video_id}.mp4"
        out_path = os.path.join(self.output_dir, filename)
        print(f"Downloading video [{video_id}] to {out_path}...")
        return self._download(url, out_path, download_type="video", video_id=video_id)

    def download_audio(self, url: str, video_id: str = "audio") -> str:
        """Downloads and converts to MP3 for Whisper transcription."""
        base_name = f"{video_id}_audio"
        out_path = os.path.join(self.output_dir, f"{base_name}.mp3")
        print(f"Downloading audio [{video_id}] to {out_path}...")
        return self._download(url, out_path, download_type="audio", video_id=video_id)
