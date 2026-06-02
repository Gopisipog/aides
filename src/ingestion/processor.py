import json
import cv2
import os
import math


class MultimodalProcessor:
    """Converts YouTube video/audio into a time-aligned text corpus."""

    def __init__(self):
        print("Initializing Multimodal Processor (local Whisper)...")
        self._whisper_model = None  # Lazy load — downloads ~140 MB on first use
        self.ocr_reader = None      # Lazy load to prevent DLL/RAM issues

    def _get_whisper_model(self):
        if self._whisper_model is None:
            import whisper
            print("Loading local Whisper model (base) — first run downloads ~140 MB...")
            self._whisper_model = whisper.load_model("base")
            print("Whisper model loaded.")
        return self._whisper_model

    def transcribe_audio(self, audio_path):
        """Uses local openai-whisper to generate transcripts with timestamps."""
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"Transcribing audio via local Whisper: {audio_path} ({file_size_mb:.1f} MB)")

        try:
            model = self._get_whisper_model()
            result = model.transcribe(audio_path, verbose=False)
        except Exception as e:
            raise RuntimeError(f"Local Whisper transcription failed: {e}") from e

        raw_segments = result.get("segments", [])
        if not raw_segments:
            raise RuntimeError(
                "Whisper returned no segments. The audio may be silent, too short, "
                "or in an unsupported format."
            )

        segments = [
            {
                "start": seg["start"],
                "end":   seg["end"],
                "text":  seg["text"].strip(),
            }
            for seg in raw_segments
        ]

        print(f"Transcription complete — {len(segments)} segments.")
        return segments

    def extract_visual_text(self, video_path, sample_rate_sec=30, enabled=False):
        """Uses EasyOCR on keyframes. Set enabled=True to activate (slow, requires EasyOCR)."""
        if not enabled:
            print("Skipping visual text extraction (pass enabled=True to activate).")
            return []

        # Try to initialize EasyOCR lazily
        if self.ocr_reader is None:
            try:
                import easyocr

                self.ocr_reader = easyocr.Reader(["en"], gpu=False)
                print("EasyOCR loaded successfully (CPU).")
            except Exception as e:
                print(
                    f"Warning: EasyOCR failed to load (Check DLLs/RAM). Skipping visual OCR. Error: {e}"
                )
                return []

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0 or fps != fps:
            fps = 30

        frame_interval = max(1, int(fps * sample_rate_sec))
        ocr_results = []
        frame_count = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                current_time_sec = frame_count / fps
                try:
                    results = self.ocr_reader.readtext(frame)
                    text = " ".join(
                        [text for (bbox, text, prob) in results if prob > 0.5]
                    )
                    if text.strip():
                        ocr_results.append(
                            {"timestamp": current_time_sec, "text": text.strip()}
                        )
                except Exception as e:
                    print(f"OCR Error on frame {frame_count}: {e}")

            frame_count += 1

        cap.release()
        return ocr_results

    def process(self, video_path, audio_path, output_json_path, enable_ocr=False, video_id="unknown"):
        """Merges audio and visual text into a timestamp-aligned JSON object.

        Each segment is stamped with ``video_id`` so the corpus can accumulate
        segments from multiple ingestions without losing attribution.
        """
        print(f"Processing multimodal data...")

        transcripts = self.transcribe_audio(audio_path)
        ocr_data = self.extract_visual_text(video_path, enabled=enable_ocr)

        # Merge logic based on Whisper segments
        new_segments = []
        for segment in transcripts:
            start_time = segment["start"]
            end_time   = segment["end"]

            relevant_ocr = [
                ocr["text"]
                for ocr in ocr_data
                if start_time <= ocr["timestamp"] <= end_time
            ]

            new_segments.append(
                {
                    "video_id":   video_id,
                    "start_time": start_time,
                    "end_time":   end_time,
                    "transcript": segment["text"],
                    "visual_text": " | ".join(relevant_ocr) if relevant_ocr else "",
                }
            )

        # Load existing corpus and append (preserving other videos)
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        existing = []
        if os.path.exists(output_json_path):
            try:
                with open(output_json_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                # Remove any prior segments for this video_id (re-ingest)
                existing = [s for s in existing if s.get("video_id") != video_id]
            except (json.JSONDecodeError, IOError):
                existing = []

        output_corpus = existing + new_segments

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(output_corpus, f, indent=4)

        print(f"Corpus saved to {output_json_path} ({len(new_segments)} new segments)")
        return new_segments
