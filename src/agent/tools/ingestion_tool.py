"""Tool for ingesting YouTube videos, live audio, or text into the knowledge graph."""

import os
import json
import datetime
from typing import Any, Dict, Optional

from src.ingestion.downloader import YouTubeDownloader
from src.ingestion.processor import MultimodalProcessor
from src.ingestion.live_audio import LiveAudioIngestor, list_audio_devices
from src.core.extractor import SemanticEntityRecognizer
from src.core.clustering import DependencyMiner
from src.core.enrichment import GraphEnrichmentEngine
from src.database.neo4j_client import Neo4jClient
from src.database.schema import Neo4jSchemaManager
from src.agent.tools.base import BaseTool

REGISTRY_PATH = "data/processed/videos_registry.json"
CORPUS_PATH = "data/processed/corpus.json"


def _load_registry():
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _save_registry(registry):
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4)


def _generate_summary(segments, meta):
    """Generate a concise summary using DeepSeek."""
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return "Summary unavailable (no DeepSeek key)."
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    full_text = " ".join(s["transcript"] for s in segments)[:3000]
    prompt = (
        f"Video title: {meta['title']}\nChannel: {meta['channel']}\n\n"
        f"Transcript excerpt:\n{full_text}\n\n"
        "Write a 3-sentence summary of what this video teaches about leadership or communication."
    )
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Summary generation error: {e}")
        return "Summary unavailable."


class IngestionTool(BaseTool):
    """Ingests a YouTube video, live audio, or text into the knowledge graph."""

    name = "ingestion_tool"
    description = (
        "Downloads, transcribes, extracts triplets, and builds a knowledge graph "
        "from YouTube videos, live microphone recordings, or text input."
    )

    def __init__(self, run_enrichment: bool = True):
        super().__init__()
        self._run_enrichment = run_enrichment

    def run(
        self,
        source_type: str = "youtube",
        url: Optional[str] = None,
        duration_sec: int = 60,
        transcript_text: Optional[str] = None,
        run_enrichment: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute ingestion pipeline.

        Args:
            source_type: "youtube", "live_audio", or "text"
            url: YouTube URL (for youtube source)
            duration_sec: Recording duration for live audio
            transcript_text: Raw text to ingest (for text source)
            run_enrichment: Whether to run graph enrichment after ingestion

        Returns:
            Dict with status, video_id, segments_count, summary, and message.
        """
        if source_type == "youtube":
            return self._ingest_youtube(url)
        elif source_type == "live_audio":
            return self._ingest_live_audio(duration_sec)
        elif source_type == "text":
            return self._ingest_text(transcript_text)
        else:
            return {
                "status": "error",
                "message": f"Unknown source_type: {source_type}. Use 'youtube', 'live_audio', or 'text'."
            }

    def _ingest_youtube(self, url: str) -> Dict[str, Any]:
        if not url:
            return {"status": "error", "message": "No URL provided for YouTube ingestion."}

        # ── Init runtime deps ────────────────────────────────────────────
        import static_ffmpeg
        from dotenv import load_dotenv
        static_ffmpeg.add_paths()
        load_dotenv()

        # ── Init DB ──────────────────────────────────────────────────────
        db = Neo4jClient()
        schema = Neo4jSchemaManager(db)
        schema.setup_constraints()

        # ── Fetch metadata ───────────────────────────────────────────────
        downloader = YouTubeDownloader()
        meta = downloader.fetch_metadata(url)
        video_id = meta["video_id"]

        # ── Download ─────────────────────────────────────────────────────
        video_path = downloader.download_video(url, video_id=video_id)
        audio_path = downloader.download_audio(url, video_id=video_id)

        # ── Transcribe ───────────────────────────────────────────────────
        processor = MultimodalProcessor()
        text_segments = processor.process(video_path, audio_path, CORPUS_PATH, video_id=video_id)
        if not text_segments:
            db.close()
            return {"status": "error", "message": "Transcription produced 0 segments."}

        # ── Summary ─────────────────────────────────────────────────────
        summary = _generate_summary(text_segments, meta)

        registry = _load_registry()
        registry = [v for v in registry if v["video_id"] != video_id]
        registry.append({**meta, "summary": summary, "segment_count": len(text_segments),
                         "ingested_at": datetime.datetime.utcnow().isoformat() + "Z"})
        _save_registry(registry)

        # ── Extract triplets ────────────────────────────────────────────
        extractor = SemanticEntityRecognizer()
        total_triplets = 0
        for idx, segment in enumerate(text_segments):
            combined_text = f"{segment['transcript']} [Visual Context: {segment.get('visual_text', '')}]"
            triplets = extractor.extract_triplets(combined_text)
            for t in triplets:
                subject_name = extractor.map_to_dbpedia(t["subject"])
                object_name = extractor.map_to_dbpedia(t["object"])
                db.insert_triplet(
                    subject=subject_name,
                    subject_type=t["subject_type"],
                    relation=t["relation"],
                    obj=object_name,
                    obj_type=t["object_type"],
                    source_time=segment["start_time"],
                    video_id=video_id,
                )
                total_triplets += 1

        # ── Dependency mining ───────────────────────────────────────────
        miner = DependencyMiner(db_client=db)
        miner.determine_prerequisites(text_segments)
        miner.detect_learning_paths(text_segments)

        # ── Enrichment ───────────────────────────────────────────────────
        if self._run_enrichment:
            enrichment = GraphEnrichmentEngine(db)
            enrichment.run_enrichment()

        db.close()

        return {
            "status": "success",
            "video_id": video_id,
            "title": meta["title"],
            "segments_count": len(text_segments),
            "triplets_extracted": total_triplets,
            "summary": summary,
            "message": f"Ingested '{meta['title']}' — {len(text_segments)} segments, {total_triplets} triplets."
        }

    def _ingest_live_audio(self, duration_sec: int) -> Dict[str, Any]:
        # Similar logic to run_live_pipeline in main.py
        ingestor = LiveAudioIngestor(device_index=0)
        devices = list_audio_devices()
        if devices and "error" not in devices[0]:
            ingestor = LiveAudioIngestor(device_index=devices[0]["index"])

        ingestor.start_recording()
        import time
        time.sleep(duration_sec)
        audio, wav_path = ingestor.stop_recording(save=True)
        segments = ingestor.transcribe_file(wav_path)

        db = Neo4jClient()
        schema = Neo4jSchemaManager(db)
        schema.setup_constraints()

        vid_id, new_segs = ingestor.append_to_corpus(segments, CORPUS_PATH)
        # Build registry entry
        registry = _load_registry()
        registry_entry = {
            "video_id": vid_id,
            "title": "Live Audio Capture",
            "url": "",
            "channel": "Live Mic",
            "thumbnail_url": "",
            "summary": f"Live microphone capture — {len(segments)} segments",
            "duration_sec": duration_sec,
            "segment_count": len(segments),
            "ingested_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        registry = [v for v in registry if v["video_id"] != vid_id]
        registry.append(registry_entry)
        _save_registry(registry)

        # Extract triplets
        extractor = SemanticEntityRecognizer()
        total_triplets = 0
        for segment in segments:
            triplets = extractor.extract_triplets(segment["transcript"])
            for t in triplets:
                subject_name = extractor.map_to_dbpedia(t["subject"])
                object_name = extractor.map_to_dbpedia(t["object"])
                db.insert_triplet(
                    subject=subject_name,
                    subject_type=t["subject_type"],
                    relation=t["relation"],
                    obj=object_name,
                    obj_type=t["object_type"],
                    source_time=segment.get("start"),
                    video_id=vid_id,
                )
                total_triplets += 1

        miner = DependencyMiner(db_client=db)
        miner.determine_prerequisites(segments)
        miner.detect_learning_paths(segments)

        if self._run_enrichment:
            enrichment = GraphEnrichmentEngine(db)
            enrichment.run_enrichment()

        db.close()

        return {
            "status": "success",
            "video_id": vid_id,
            "title": "Live Audio Capture",
            "segments_count": len(segments),
            "triplets_extracted": total_triplets,
            "duration_sec": duration_sec,
            "summary": registry_entry["summary"],
            "message": f"Ingested live audio ({duration_sec}s) — {len(segments)} segments, {total_triplets} triplets."
        }

    def _ingest_text(self, text: str) -> Dict[str, Any]:
        if not text:
            return {"status": "error", "message": "No text provided for ingestion."}

        db = Neo4jClient()
        schema = Neo4jSchemaManager(db)
        schema.setup_constraints()

        # Treat as a single segment
        video_id = f"text_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        segment = {
            "start_time": 0.0,
            "end_time": 0.0,
            "transcript": text,
            "visual_text": "",
        }

        extractor = SemanticEntityRecognizer()
        triplets = extractor.extract_triplets(text)
        total_triplets = 0
        for t in triplets:
            subject_name = extractor.map_to_dbpedia(t["subject"])
            object_name = extractor.map_to_dbpedia(t["object"])
            db.insert_triplet(
                subject=subject_name,
                subject_type=t["subject_type"],
                relation=t["relation"],
                obj=object_name,
                obj_type=t["object_type"],
                source_time=0.0,
                video_id=video_id,
            )
            total_triplets += 1

        if self._run_enrichment:
            enrichment = GraphEnrichmentEngine(db)
            enrichment.run_enrichment()

        db.close()

        return {
            "status": "success",
            "video_id": video_id,
            "title": "Text Input Ingestion",
            "segments_count": 1,
            "triplets_extracted": total_triplets,
            "summary": "Text-based ingestion — no summary generated.",
            "message": f"Ingested text — {total_triplets} triplets extracted."
        }