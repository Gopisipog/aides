import yt_dlp
import os

class YouTubeDownloader:
    """Wrapper for yt-dlp to download video and audio from YouTube URLs."""

    def __init__(self, output_dir="data/raw"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def fetch_metadata(self, url):
        """Fetches video title, channel, thumbnail and duration without downloading."""
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "video_id":     info.get("id", "unknown"),
            "title":        info.get("title", "Unknown Title"),
            "url":          url,
            "thumbnail_url": info.get("thumbnail", ""),
            "channel":      info.get("uploader", "Unknown"),
            "duration_sec": info.get("duration", 0),
        }

    def _ffmpeg_dir(self):
        """Returns the directory containing the ffmpeg binary (yt-dlp expects a dir, not a file path)."""
        import shutil
        ffmpeg_bin = shutil.which('ffmpeg')
        return os.path.dirname(ffmpeg_bin) if ffmpeg_bin else None

    def download_video(self, url, video_id="video"):
        """Downloads the video file for OCR processing."""
        filename = f"{video_id}.mp4"
        out_path  = os.path.join(self.output_dir, filename)
        print(f"Downloading video [{video_id}] to {out_path}...")

        ydl_opts = {
            # Prefer pre-muxed mp4; fall back to best available and let ffmpeg mux
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': out_path,
            'ffmpeg_location': self._ffmpeg_dir(),
            'overwrites': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not os.path.exists(out_path):
            raise FileNotFoundError(f"Video download failed — file not found: {out_path}")
        return out_path

    def download_audio(self, url, video_id="audio"):
        """Downloads and converts to MP3 for Whisper transcription."""
        base_name = f"{video_id}_audio"
        out_path  = os.path.join(self.output_dir, f"{base_name}.mp3")
        print(f"Downloading audio [{video_id}] to {out_path}...")

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(self.output_dir, base_name),
            'ffmpeg_location': self._ffmpeg_dir(),
            'overwrites': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not os.path.exists(out_path):
            raise FileNotFoundError(f"Audio download failed — file not found: {out_path}")
        return out_path
