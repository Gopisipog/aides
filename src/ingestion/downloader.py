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

    def download_video(self, url: str, video_id: str = "video") -> str:
        """Downloads the video file for OCR processing.

        Retries with different client types if 403 is encountered.
        """
        filename = f"{video_id}.mp4"
        out_path = os.path.join(self.output_dir, filename)
        print(f"Downloading video [{video_id}] to {out_path}...")

        client_types = ["android", "web", "mweb"]
        last_error = None

        for client in client_types:
            try:
                opts = self._get_base_opts()
                opts["extractor_args"]["youtube"]["player_client"] = [client]
                opts["format"] = (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
                )
                opts["outtmpl"] = out_path
                opts["ffmpeg_location"] = self._ffmpeg_dir()
                opts["overwrites"] = True
                opts["noplaylist"] = True
                opts["quiet"] = True
                opts["no_warnings"] = True

                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

                if not os.path.exists(out_path):
                    raise FileNotFoundError(
                        f"Video download failed — file not found: {out_path}"
                    )
                return out_path

            except Exception as e:
                last_error = e
                if "403" not in str(e):
                    raise

        raise RuntimeError(
            f"Failed to download video {url} after trying clients "
            f"{client_types}: {last_error}"
        )

    def download_audio(self, url: str, video_id: str = "audio") -> str:
        """Downloads and converts to MP3 for Whisper transcription.

        Retries with different client types if 403 is encountered.
        """
        base_name = f"{video_id}_audio"
        out_path = os.path.join(self.output_dir, f"{base_name}.mp3")
        print(f"Downloading audio [{video_id}] to {out_path}...")

        client_types = ["android", "web", "mweb"]
        last_error = None

        for client in client_types:
            try:
                opts = self._get_base_opts()
                opts["extractor_args"]["youtube"]["player_client"] = [client]
                opts["format"] = "bestaudio/best"
                opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ]
                opts["outtmpl"] = os.path.join(self.output_dir, base_name)
                opts["ffmpeg_location"] = self._ffmpeg_dir()
                opts["overwrites"] = True
                opts["noplaylist"] = True
                opts["quiet"] = True
                opts["no_warnings"] = True

                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

                if not os.path.exists(out_path):
                    raise FileNotFoundError(
                        f"Audio download failed — file not found: {out_path}"
                    )
                return out_path

            except Exception as e:
                last_error = e
                if "403" not in str(e):
                    raise

        raise RuntimeError(
            f"Failed to download audio {url} after trying clients "
            f"{client_types}: {last_error}"
        )
