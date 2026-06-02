import os
import sys
import json
import argparse
import datetime

# Ensure stdout/stderr use UTF-8 on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv

# Ensure ffmpeg is available in PATH (static_ffmpeg for local, system ffmpeg for cloud/CI)
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass  # skip if read-only venv (Streamlit Cloud) or static_ffmpeg not installed

from src.ingestion.downloader import YouTubeDownloader
from src.ingestion.processor import MultimodalProcessor
from src.ingestion.live_audio import LiveAudioIngestor, list_audio_devices
from src.core.extractor import SemanticEntityRecognizer
from src.core.clustering import DependencyMiner
from src.core.enrichment import GraphEnrichmentEngine
from src.database.neo4j_client import Neo4jClient
from src.database.schema import Neo4jSchemaManager

# Load environment variables (API keys, DB credentials)
load_dotenv()

REGISTRY_PATH = "data/processed/videos_registry.json"
CORPUS_PATH   = "data/processed/corpus.json"


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


def _add_live_registry(video_id, segments, duration_sec=0):
    import datetime as _dt
    registry = _load_registry()
    registry = [v for v in registry if v["video_id"] != video_id]
    registry.append({
        "video_id": video_id,
        "title": "Live Audio Capture (CLI)",
        "url": "",
        "channel": "Live Mic",
        "thumbnail_url": "",
        "summary": f"Live CLI microphone capture — {len(segments)} segments",
        "duration_sec": duration_sec,
        "segment_count": len(segments),
        "ingested_at": _dt.datetime.utcnow().isoformat() + "Z",
    })
    _save_registry(registry)


def _generate_summary(segments, meta):
    """Generates a concise summary of the video using DeepSeek."""
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return "Summary unavailable (no DeepSeek key)."
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Use up to ~3 000 chars of transcript
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


def run_pipeline(url, progress_cb=None):
    """Executes the full Multimodal Knowledge Graph Pipeline.

    Args:
        url: YouTube video URL.
        progress_cb: optional callable(fraction: float, label: str) for UI updates.
    """
    def _progress(frac, label):
        print(f"[{int(frac*100):3d}%] {label}")
        if progress_cb:
            progress_cb(frac, label)

    _progress(0.0, "Starting pipeline...")

    # ── Init DB ──────────────────────────────────────────────────────────────
    db = Neo4jClient()
    schema = Neo4jSchemaManager(db)
    schema.setup_constraints()

    # ── Phase 0: Fetch video metadata ────────────────────────────────────────
    _progress(0.05, "Fetching video metadata...")
    downloader = YouTubeDownloader()
    meta = downloader.fetch_metadata(url)
    video_id = meta["video_id"]
    print(f"  -> {meta['title']}  [{video_id}]")

    # ── Phase 1a: Download video ─────────────────────────────────────────────
    _progress(0.10, f"Downloading video: {meta['title'][:50]}...")
    video_path = downloader.download_video(url, video_id=video_id)

    # ── Phase 1b: Download audio ─────────────────────────────────────────────
    _progress(0.20, "Downloading audio...")
    audio_path = downloader.download_audio(url, video_id=video_id)

    # ── Phase 1c: Transcribe & extract visual text ───────────────────────────
    _progress(0.30, "Transcribing audio (Whisper)...")
    processor = MultimodalProcessor()
    text_segments = processor.process(
        video_path, audio_path, CORPUS_PATH, video_id=video_id
    )

    if not text_segments:
        raise RuntimeError(
            "Transcription produced 0 segments — video not ingested. "
            "Check your OpenAI API quota and audio file."
        )

    # ── Generate & store summary ─────────────────────────────────────────────
    _progress(0.40, f"Summarising video ({len(text_segments)} segments)...")
    summary = _generate_summary(text_segments, meta)

    registry = _load_registry()
    registry = [v for v in registry if v["video_id"] != video_id]
    registry.append({
        **meta,
        "summary":       summary,
        "segment_count": len(text_segments),
        "ingested_at":   datetime.datetime.utcnow().isoformat() + "Z",
    })
    _save_registry(registry)
    print(f"Registry updated ({len(registry)} video(s) total).")

    # ── Phase 2 & 3: Triplet Extraction & Graph Insertion ───────────────────
    extractor = SemanticEntityRecognizer()
    total_segs = len(text_segments)
    for idx, segment in enumerate(text_segments):
        frac = 0.40 + 0.25 * ((idx + 1) / max(total_segs, 1))
        _progress(frac, f"Extracting triplets — segment {idx+1}/{total_segs}...")
        combined_text = (
            f"{segment['transcript']} [Visual Context: {segment['visual_text']}]"
        )
        triplets = extractor.extract_triplets(combined_text)

        for t in triplets:
            subject_name = extractor.map_to_dbpedia(t["subject"])
            object_name  = extractor.map_to_dbpedia(t["object"])
            db.insert_triplet(
                subject=subject_name,
                subject_type=t["subject_type"],
                relation=t["relation"],
                obj=object_name,
                obj_type=t["object_type"],
                source_time=segment["start_time"],
                video_id=video_id,
            )

    # ── Phase 4: Dependency mining & path detection ──────────────────────────
    _progress(0.65, "Mining prerequisites and learning paths...")
    miner = DependencyMiner(db_client=db)
    miner.determine_prerequisites(text_segments)
    miner.detect_learning_paths(text_segments)

    # ── Phase 5: Graph enrichment (A-F) ─────────────────────────────────────
    _progress(0.75, "Running graph enrichment (strategies, tactics, paths)...")
    enrichment = GraphEnrichmentEngine(db)
    enrichment.run_enrichment()

    db.close()
    _progress(1.0, "Pipeline complete!")
    print("\nPipeline Complete!")


def run_live_pipeline(duration_sec=60, progress_cb=None):
    """Record live microphone audio, transcribe with Whisper, and build the KG."""
    def _progress(frac, label):
        print(f"[{int(frac*100):3d}%] {label}")
        if progress_cb:
            progress_cb(frac, label)

    _progress(0.0, "Initialising live audio ingestor…")

    # List devices
    devices = list_audio_devices()
    if not devices or "error" in devices[0]:
        print("No audio input devices found.")
        return
    for d in devices:
        print(f"  Device {d.get('index','?')}: {d.get('name','?')}")

    ingestor = LiveAudioIngestor(device_index=devices[0]["index"])

    # ── Record ──────────────────────────────────────────────────────────────
    _progress(0.05, f"Recording for {duration_sec} seconds…")
    ingestor.start_recording()
    import time as _time
    _time.sleep(duration_sec)
    audio, wav_path = ingestor.stop_recording(save=True)
    print(f"Recording saved to {wav_path}")
    _progress(0.30, "Transcribing with Whisper…")
    segments = ingestor.transcribe_file(wav_path)
    print(f"Transcription complete — {len(segments)} segment(s).")
    _progress(0.40, "Appending to corpus…")
    vid_id, new_segs = ingestor.append_to_corpus(segments, CORPUS_PATH)
    _add_live_registry(vid_id, segments, duration_sec)
    _progress(0.45, "Extracting triplets…")

    # ── DB ──────────────────────────────────────────────────────────────────
    db = Neo4jClient()
    schema = Neo4jSchemaManager(db)
    schema.setup_constraints()
    extractor = SemanticEntityRecognizer()
    miner = DependencyMiner(db_client=db)
    enrichment = GraphEnrichmentEngine(db)

    total = len(segments)
    for idx, segment in enumerate(segments):
        frac = 0.45 + 0.25 * ((idx + 1) / max(total, 1))
        _progress(frac, f"Extracting triplets — segment {idx+1}/{total}…")
        combined_text = segment["transcript"]
        triplets = extractor.extract_triplets(combined_text)
        for t in triplets:
            subject_name = extractor.map_to_dbpedia(t["subject"])
            object_name  = extractor.map_to_dbpedia(t["object"])
            db.insert_triplet(
                subject=subject_name,
                subject_type=t["subject_type"],
                relation=t["relation"],
                obj=object_name,
                obj_type=t["object_type"],
                source_time=segment["start"],
                video_id=vid_id,
            )

    _progress(0.70, "Mining prerequisites…")
    miner.determine_prerequisites(segments)
    miner.detect_learning_paths(segments)

    _progress(0.80, "Running graph enrichment…")
    enrichment.run_enrichment()

    db.close()
    _progress(1.0, "Pipeline complete!")
    print("\nLive Audio Pipeline Complete!")


def run_agent_cli():
    """Run the agent in interactive CLI mode."""
    from src.agent import AIDESOrchestrator

    print("╔═══════════════════════════════════════════╗")
    print("║     AIDE — Agentic Instructional Design   ║")
    print("║     Interactive CLI (type 'exit' to quit) ║")
    print("╚═══════════════════════════════════════════╝")
    print()
    print("Type 'help' or '?' to see what I can do.")
    print()

    agent = AIDESOrchestrator(use_persistence=True)
    try:
        while True:
            try:
                user_input = input("👤 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break

            result = agent.process(user_input)
            status = result.get("status", "info")
            message = result.get("message", "No response.")
            intent = result.get("intent", "unknown")

            # Color-code by status
            if status == "error":
                prefix = "❌"
            elif status == "success":
                prefix = "✅"
            else:
                prefix = "🤖"

            print(f"{prefix} [{intent}] {message}")
            print()
    finally:
        agent.close()


def run_agent_query(query: str):
    """Run a single agent query and print the result."""
    from src.agent import AIDESOrchestrator

    agent = AIDESOrchestrator(use_persistence=False)
    try:
        result = agent.process(query)
        print(result.get("message", "No response."))
    finally:
        agent.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AIDE — Agentic Instructional Design Engine"
    )
    parser.add_argument("--url", type=str, help="YouTube Video URL (legacy pipeline)")
    parser.add_argument("--live", action="store_true", help="Run live audio ingestion (legacy pipeline)")
    parser.add_argument("--duration", type=int, default=60,
                        help="Recording duration in seconds (default: 60)")
    parser.add_argument("--agent", action="store_true", help="Run agent in interactive CLI mode")
    parser.add_argument("--query", type=str, help="Run agent with a single query and exit")
    args = parser.parse_args()

    if args.agent:
        run_agent_cli()
    elif args.query:
        run_agent_query(args.query)
    elif args.live:
        run_live_pipeline(duration_sec=args.duration)
    elif args.url:
        run_pipeline(args.url)
    else:
        parser.print_help()
        print()
        print("New agent mode:")
        print("  python main.py --agent        (interactive chat)")
        print("  python main.py --query \"...\"  (single query)")
