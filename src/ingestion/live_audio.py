import os
import json
import time
import threading
import numpy as np

AUDIO_DIR = "data/live_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)


def list_audio_devices():
    """List all available audio input devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        inputs = []
        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                inputs.append({
                    "index": idx,
                    "name": dev["name"],
                    "channels": dev["max_input_channels"],
                    "samplerate": int(dev["default_samplerate"]),
                })
        return inputs
    except Exception as e:
        return [{"error": str(e)}]


class LiveAudioIngestor:
    """Captures live microphone audio and transcribes with Whisper in real-time.

    Two modes:
      - **Record mode**: capture audio to a WAV file, then transcribe the whole file.
      - **Stream mode**: continuously transcribe overlapping windows, yielding
        partial results as they become available.
    """

    def __init__(self, device_index=None, samplerate=16000, channels=1):
        self.device_index = device_index
        self.samplerate = samplerate
        self.channels = channels
        self._whisper_model = None
        self._recording = []       # raw float32 samples during record
        self._is_recording = False
        self._stream = None
        self._stream_thread = None

    def _get_whisper_model(self):
        if self._whisper_model is None:
            import whisper
            print("Loading local Whisper model (base) for live audio…")
            self._whisper_model = whisper.load_model("base")
        return self._whisper_model

    # ── Recording (capture → file → transcribe) ────────────────────────────

    def start_recording(self):
        """Begin capturing microphone audio into an internal buffer."""
        import sounddevice as sd
        self._recording = []
        self._is_recording = True

        def callback(indata, frames, time_info, status):
            if status:
                print(f"Audio callback status: {status}")
            if self._is_recording:
                self._recording.append(indata.copy())

        self._stream = sd.InputStream(
            device=self.device_index,
            samplerate=self.samplerate,
            channels=self.channels,
            callback=callback,
            dtype="float32",
        )
        self._stream.start()
        print("Live audio recording started…")

    def stop_recording(self, save=True):
        """Stop capture, optionally save WAV, return raw audio array."""
        self._is_recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._recording:
            print("No audio captured.")
            return None

        audio = np.concatenate(self._recording, axis=0).flatten()
        self._recording = []

        if save:
            path = self._save_wav(audio)
            print(f"Recording saved to {path}")
            return audio, path
        return audio, None

    def _save_wav(self, audio, prefix="live"):
        import soundfile as sf
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(AUDIO_DIR, f"{prefix}_{timestamp}.wav")
        sf.write(path, audio, self.samplerate)
        return path

    def transcribe_file(self, audio_path, language=None):
        """Transcribe a saved WAV file with Whisper, returns segment list."""
        print(f"Transcribing live audio file: {audio_path}")
        model = self._get_whisper_model()
        result = model.transcribe(audio_path, verbose=False, language=language)
        segments = [
            {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
            for seg in result.get("segments", [])
        ]
        print(f"Transcription complete — {len(segments)} segments.")
        return segments

    def record_and_transcribe(self, language=None):
        """Convenience: record until stopped, then transcribe."""
        self.start_recording()
        print("Recording… (call stop_recording() when done)")
        # Block until stopped (user calls stop externally)
        while self._is_recording:
            time.sleep(0.1)
        audio, path = self.stop_recording(save=True)
        if audio is None:
            return []
        return self.transcribe_file(path, language=language)

    # ── Streaming transcription ────────────────────────────────────────────

    def transcribe_stream(self, window_sec=30, stride_sec=5, language=None,
                          callback=None):
        """Continuously capture and transcribe in overlapping windows.

        Yields ``(segment_list)`` for each new window processed.
        If *callback* is provided, it is called with each new segment list.
        """
        import sounddevice as sd
        window_samples = int(self.samplerate * window_sec)
        stride_samples = int(self.samplerate * stride_sec)
        buffer = np.zeros(window_samples, dtype="float32")
        insert_pos = 0
        segment_counter = 0
        time_offset = 0.0
        self._is_recording = True

        def callback(indata, frames, time_info, status):
            nonlocal insert_pos, segment_counter, time_offset
            if status:
                print(f"Stream status: {status}")
            if not self._is_recording:
                return

            chunk = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()
            chunk_len = len(chunk)
            if insert_pos + chunk_len < window_samples:
                buffer[insert_pos:insert_pos + chunk_len] = chunk
                insert_pos += chunk_len
            else:
                # Buffer full — transcribe
                space_left = window_samples - insert_pos
                buffer[insert_pos:] = chunk[:space_left]
                leftover = chunk[space_left:]

                # Transcribe current window
                audio_copy = buffer.copy()
                t = threading.Thread(
                    target=self._transcribe_and_report,
                    args=(audio_copy, time_offset, callback, language),
                    daemon=True,
                )
                t.start()

                # Shift buffer by stride and keep trailing audio
                shift = stride_samples
                if shift < window_samples:
                    buffer[:-shift] = buffer[shift:]
                    buffer[-shift:] = 0
                else:
                    buffer[:] = 0

                time_offset += stride_sec
                segment_counter += 1

                # Insert leftover into shifted buffer
                leftover_len = len(leftover)
                if leftover_len > 0:
                    if leftover_len < window_samples:
                        buffer[:leftover_len] = leftover
                    insert_pos = leftover_len
                else:
                    insert_pos = 0

        self._stream = sd.InputStream(
            device=self.device_index,
            samplerate=self.samplerate,
            channels=self.channels,
            callback=callback,
            dtype="float32",
            blocksize=int(self.samplerate * stride_sec),
        )
        self._stream.start()

        try:
            while self._is_recording:
                time.sleep(0.1)
        finally:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        # Transcribe any remaining audio in buffer
        remaining = buffer[:insert_pos]
        if np.any(remaining):
            self._transcribe_and_report(remaining, time_offset, callback, language)

    def stop_stream(self):
        """Gracefully stop the streaming transcription."""
        self._is_recording = False

    def _transcribe_and_report(self, audio, time_offset, callback, language):
        """Run Whisper on an audio window and report segments."""
        try:
            import whisper
            model = self._get_whisper_model()
            audio_float = audio.astype(np.float32)
            result = model.transcribe(audio_float, verbose=False, language=language)

            segments = [
                {
                    "start": round(seg["start"] + time_offset, 2),
                    "end":   round(seg["end"] + time_offset, 2),
                    "text":  seg["text"].strip(),
                }
                for seg in result.get("segments", [])
            ]
            if segments and callback:
                callback(segments)
        except Exception as e:
            print(f"Stream transcription error: {e}")

    # ── Save stream segments to corpus ─────────────────────────────────────

    def append_to_corpus(self, segments, corpus_path, source_label="live_audio"):
        """Append live audio segments to the shared corpus JSON.

        Each segment is tagged with a ``video_id`` of ``live_<timestamp>`` so
        the corpus can distinguish live captures from YouTube videos.
        """
        video_id = f"live_{int(time.time())}"

        new_segments = [
            {
                "video_id":    video_id,
                "start_time":  seg["start"],
                "end_time":    seg["end"],
                "transcript":  seg["text"],
                "visual_text": "",
                "source":      source_label,
            }
            for seg in segments
        ]

        os.makedirs(os.path.dirname(corpus_path), exist_ok=True)
        existing = []
        if os.path.exists(corpus_path):
            with open(corpus_path, "r", encoding="utf-8") as f:
                existing = json.load(f)

        output = existing + new_segments
        with open(corpus_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=4)

        print(f"Live audio corpus updated — {len(new_segments)} segment(s) appended.")
        return video_id, new_segments
