"""
AIDE — Agentic Instructional Design Engine
Streamlit Chat Interface

The primary entry point for interacting with the AI agent.
"""

import json
import os
import traceback
import uuid
import socket
from datetime import datetime

import streamlit as st

# ── Load configuration ───────────────────────────────────────────────────────
# Priority: Streamlit secrets > .env file > environment variables
from dotenv import load_dotenv

load_dotenv()  # .env is fallback for local dev; Streamlit secrets override

# ── Cloud detection ──────────────────────────────────────────────────────────
def _is_streamlit_cloud() -> bool:
    """Detect if running on Streamlit Community Cloud."""
    hostname = socket.gethostname()
    return any(marker in os.environ.get("STREAMLIT_SERVER_HEADER", "")
               for marker in ["streamlit", "share"]) or "streamlit" in hostname.lower()

IS_CLOUD = os.environ.get("AIDE_DEPLOYMENT", "").lower() == "cloud" or _is_streamlit_cloud()

# ── Ensure ffmpeg is available in PATH ───────────────────────────────────────
# On Streamlit Cloud, ffmpeg is installed via apt-get (packages.txt).
# On local Windows, use shutil.which() to find it.
# static_ffmpeg is NOT imported at module level because it tries to write
# a lock file to the venv directory, which is read-only on Streamlit Cloud.
import shutil
if not shutil.which("ffmpeg"):
    import warnings
    warnings.warn("ffmpeg not found in PATH. Install ffmpeg or ensure it's available.")

# ── Cloud detection ──────────────────────────────────────────────────────────
def _is_streamlit_cloud() -> bool:
    """Detect if running on Streamlit Community Cloud."""
    hostname = socket.gethostname()
    # Streamlit Cloud uses 'share.streamlit.io' or internal hostnames
    return any(marker in os.environ.get("STREAMLIT_SERVER_HEADER", "")
               for marker in ["streamlit", "share"]) or "streamlit" in hostname.lower()

IS_CLOUD = os.environ.get("AIDE_DEPLOYMENT", "").lower() == "cloud" or _is_streamlit_cloud()

# Load secrets: Streamlit secrets take priority if available
def _get_secret(key: str, default: str = "") -> str:
    """Get a secret from Streamlit Cloud secrets, .env, or environment."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

from src.agent import AIDESOrchestrator
from src.database.neo4j_client import Neo4jClient
from src.core.proactive import ProactiveLearningEngine
from src.ingestion.live_audio import LiveAudioIngestor, list_audio_devices

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AIDE — Agentic Instructional Design Engine",
    page_icon="🧠",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        /* Chat message styling */
        .chat-user {
            background-color: #e3f2fd;
            border-radius: 16px 16px 4px 16px;
            padding: 10px 16px;
            margin: 8px 0;
            border-left: 4px solid #1976D2;
        }
        .chat-assistant {
            background-color: #f5f5f5;
            border-radius: 16px 16px 16px 4px;
            padding: 10px 16px;
            margin: 8px 0;
            border-left: 4px solid #4CAF50;
        }
        .chat-tool-call {
            background-color: #fff3e0;
            border-radius: 8px;
            padding: 6px 12px;
            margin: 4px 0 4px 24px;
            border-left: 3px solid #FF9800;
            font-size: 0.85em;
        }
        .chat-intent-badge {
            display: inline-block;
            background: #607D8B;
            color: white;
            padding: 1px 8px;
            border-radius: 8px;
            font-size: 0.65em;
            margin-right: 6px;
        }
        .stApp header {display: none;}
    </style>
""",
    unsafe_allow_html=True,
)

# ── Session State Init ───────────────────────────────────────────────────────
if "agent" not in st.session_state:
    st.session_state.agent = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]


def get_or_create_agent() -> AIDESOrchestrator:
    """Lazy-init the agent singleton in session state."""
    if st.session_state.agent is None:
        with st.spinner("Initializing agent…"):
            agent = AIDESOrchestrator(use_persistence=True)
            st.session_state.agent = agent
            st.session_state.session_id = agent.session_id
    return st.session_state.agent


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/brain.png", width=48)
    st.markdown("## 🧠 AIDE")
    st.caption("Agentic Instructional Design Engine")
    st.divider()

    # Session info
    st.markdown(f"**Session:** `{st.session_state.session_id}`")
    st.markdown(f"**Messages:** {len(st.session_state.messages)}")

    # Graph Statistics
    st.divider()
    st.markdown("### 📊 Graph Stats")
    db = Neo4jClient()
    node_count = 0
    rel_count = 0
    if db.driver:
        try:
            nodes = db.execute_read("MATCH (n) RETURN count(n) as count")
            node_count = nodes[0]["count"] if nodes else 0
            rels = db.execute_read("MATCH ()-[r]->() RETURN count(r) as count")
            rel_count = rels[0]["count"] if rels else 0
        except Exception:
            pass
        db.close()

    col1, col2 = st.columns(2)
    col1.metric("Nodes", node_count)
    col2.metric("Relationships", rel_count)

    st.divider()
    st.markdown("### ⚡ Quick Actions")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Help", use_container_width=True):
            agent = get_or_create_agent()
            result = agent.process("help")
            st.session_state.messages.append({
                "role": "user",
                "content": "help",
                "timestamp": datetime.now().isoformat(),
            })
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.get("message", ""),
                "intent": "help",
                "timestamp": datetime.now().isoformat(),
            })
            st.rerun()
    with col_b:
        if st.button("Stats", use_container_width=True):
            agent = get_or_create_agent()
            result = agent.process("Show me graph statistics")
            st.session_state.messages.append({
                "role": "user",
                "content": "Show me graph statistics",
                "timestamp": datetime.now().isoformat(),
            })
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.get("message", ""),
                "intent": "stats",
                "data": result.get("data"),
                "timestamp": datetime.now().isoformat(),
            })
            st.rerun()

    if st.button("Clear Chat", type="secondary", use_container_width=True):
        st.session_state.messages = []
        if st.session_state.agent:
            st.session_state.agent.chat_memory.clear()
        st.rerun()

    if st.button("Reset Agent", type="secondary", use_container_width=True):
        if st.session_state.agent:
            st.session_state.agent.close()
        st.session_state.agent = None
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())[:8]
        st.rerun()


# ── Main Interface: Tabs ─────────────────────────────────────────────────────
tab_chat, tab_knowledge, tab_strategy, tab_search, tab_live = st.tabs(
    ["💬 Agent Chat", "📚 Ingested Knowledge", "🗺 Strategy Map", "🔍 Graph Search", "🎙 Live Audio"]
)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: Agent Chat (Primary)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown("## 💬 AIDE Agent Chat")
    st.caption(
        "Ask me anything about leadership, or tell me to ingest a video, "
        "search the knowledge graph, enrich the graph, or give you learning insights."
    )

    # ── Initialize agent ────────────────────────────────────────────────────
    agent = get_or_create_agent()

    # ── Render chat history ─────────────────────────────────────────────────
    chat_container = st.container(height=500)

    with chat_container:
        # Welcome message if no messages
        if not st.session_state.messages:
            st.markdown(
                "<div class='chat-assistant'>"
                "<b>👋 Welcome to AIDE!</b><br><br>"
                "I'm your Agentic Instructional Design Engine. I can help you:<br>"
                "• 📥 **Ingest** YouTube videos, live audio, or text into the knowledge graph<br>"
                "• 🔍 **Search** the knowledge graph for concepts, strategies, and tactics<br>"
                "• 🧠 **Enrich** the graph with new insights and learning paths<br>"
                "• 💡 **Answer** leadership questions with graph-grounded context<br><br>"
                "Try: <i>\"Ingest this YouTube video: https://youtube.com/watch?v=...\"</i><br>"
                "Or: <i>\"Search for emotional intelligence\"</i><br>"
                "Or: <i>\"What is servant leadership?\"</i><br>"
                "Or: <i>\"Enrich the knowledge graph\"</i><br>"
                "</div>",
                unsafe_allow_html=True,
            )

        for msg in st.session_state.messages:
            role = msg["role"]
            content = msg.get("content", "")
            intent = msg.get("intent", "")

            if role == "user":
                st.markdown(
                    f"<div class='chat-user'>"
                    f"<span class='chat-intent-badge'>YOU</span> {content}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                intent_badge = f"<span class='chat-intent-badge'>{intent.upper()}</span>" if intent else ""
                st.markdown(
                    f"<div class='chat-assistant'>"
                    f"<span class='chat-intent-badge'>AIDE</span> {intent_badge}"
                    f"<br>{content}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Show structured data if available
                data = msg.get("data")
                if data:
                    if isinstance(data, list) and len(data) > 0:
                        with st.expander("📊 View structured data", expanded=False):
                            st.json(data)
                    elif isinstance(data, dict):
                        with st.expander("📊 View structured data", expanded=False):
                            st.json(data)

    # ── Chat input ──────────────────────────────────────────────────────────
    col_input, col_send = st.columns([6, 1])
    with col_input:
        user_input = st.text_input(
            "Your message:",
            placeholder="Ask me anything...",
            label_visibility="collapsed",
            key="chat_input",
            on_change=None,
        )
    with col_send:
        send_clicked = st.button("Send", type="primary", use_container_width=True)

    # Handle input submission
    if user_input and send_clicked:
        # Add user message to session
        st.session_state.messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat(),
        })

        # Process through agent
        with st.spinner("Thinking..."):
            try:
                result = agent.process(user_input)
                response_text = result.get("message", "I'm not sure how to respond to that.")
                intent = result.get("intent", "chat")
                data = result.get("data")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "intent": intent,
                    "data": data,
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as e:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"❌ Error: {str(e)}",
                    "intent": "error",
                    "timestamp": datetime.now().isoformat(),
                })

        st.rerun()

    # ── Example prompts ──────────────────────────────────────────────────────
    st.divider()
    st.markdown("**💡 Example prompts:**")
    examples = [
        "Ingest this YouTube video: https://youtube.com/watch?v=jfW6gL6hKhk",
        "Search for emotional intelligence in the graph",
        "What is servant leadership?",
        "Show me graph statistics",
        "Enrich the knowledge graph",
        "Record live audio for 30 seconds",
        "Tell me about conflict resolution",
    ]
    cols = st.columns(len(examples))
    for i, example in enumerate(examples):
        with cols[i]:
            if st.button(example[:30] + "...", key=f"ex_{i}", help=example, use_container_width=True):
                st.session_state.messages.append({
                    "role": "user",
                    "content": example,
                    "timestamp": datetime.now().isoformat(),
                })
                with st.spinner("Thinking..."):
                    try:
                        result = agent.process(example)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": result.get("message", ""),
                            "intent": result.get("intent", "chat"),
                            "data": result.get("data"),
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception as e:
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"❌ Error: {str(e)}",
                            "intent": "error",
                            "timestamp": datetime.now().isoformat(),
                        })
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: Ingested Knowledge (existing functionality)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_knowledge:
    REGISTRY_PATH = "data/processed/videos_registry.json"
    CORPUS_PATH = "data/processed/corpus.json"

    TYPE_COLORS = {
        "Competency": "#2196F3",
        "Concept": "#4CAF50",
        "Outcome": "#FF9800",
        "Personality": "#9C27B0",
        "Strategy": "#FF5722",
        "Tactic": "#E91E63",
        "Path": "#00BCD4",
    }

    def pill(name, color):
        return (
            f"<span style='background:{color};color:white;padding:2px 10px;"
            f"border-radius:12px;font-size:0.82em;margin:2px;display:inline-block'>"
            f"{name}</span>"
        )

    registry = []
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)

    corpus = []
    if os.path.exists(CORPUS_PATH):
        with open(CORPUS_PATH, "r", encoding="utf-8") as f:
            corpus = json.load(f)

    st.markdown("## 📚 Ingested Knowledge")
    st.caption("Browse all videos that have been ingested into the knowledge graph.")

    if not registry:
        st.info("No videos ingested yet. Use the Agent Chat to ingest content.")
    else:
        st.markdown(f"### {len(registry)} Video(s) Ingested")
        for vid in registry:
            vid_id = vid["video_id"]
            segs = [s for s in corpus if s.get("video_id") == vid_id]
            duration = vid.get("duration_sec", 0)
            mins, secs = divmod(int(duration), 60)
            ingested = vid.get("ingested_at", "")[:10]

            with st.container(border=True):
                thumb_col, info_col = st.columns([1, 3])
                with thumb_col:
                    if vid.get("thumbnail_url"):
                        st.image(vid["thumbnail_url"], use_container_width=True)
                with info_col:
                    st.markdown(f"#### [{vid['title']}]({vid['url']})")
                    st.caption(
                        f"📺 {vid.get('channel', '—')}  &nbsp;|&nbsp;  "
                        f"⏱ {mins}m {secs}s  &nbsp;|&nbsp;  "
                        f"📅 Ingested {ingested}  &nbsp;|&nbsp;  "
                        f"🆔 `{vid_id}`"
                    )
                    st.markdown(f"> {vid.get('summary', '')}")

                m1, m2, m3 = st.columns(3)
                m1.metric("Transcript Segments", len(segs))
                m2.metric("Duration", f"{mins}m {secs}s")
                m3.metric(
                    "Visual Text Segments", sum(1 for s in segs if s.get("visual_text"))
                )

                # Graph data for this video
                db = Neo4jClient()
                if db.driver:
                    vid_nodes = (
                        db.execute_read(
                            """
                        MATCH (a)-[r]->(b)
                        WHERE r.video_id = $vid_id
                          AND a.name IS NOT NULL AND b.name IS NOT NULL
                        RETURN labels(a)[0] AS from_type, a.name AS from_name,
                               type(r)      AS relation,
                               labels(b)[0] AS to_type,  b.name AS to_name,
                               r.source_time AS time
                        ORDER BY r.source_time
                        """,
                            {"vid_id": vid_id},
                        )
                        or []
                    )

                    if vid_nodes:
                        EXTRACTED_TYPES = {"Competency", "Concept"}
                        ENRICHED_TYPES = {"Strategy", "Tactic", "Path", "Outcome", "Personality"}

                        extracted_groups: dict = {}
                        enriched_groups: dict = {}

                        for row in vid_nodes:
                            for ntype, name in [
                                (row["from_type"], row["from_name"]),
                                (row["to_type"], row["to_name"]),
                            ]:
                                if name.startswith("http://") or name.startswith("https://"):
                                    continue
                                if ntype in EXTRACTED_TYPES:
                                    extracted_groups.setdefault(ntype, set()).add(name)
                                elif ntype in ENRICHED_TYPES:
                                    enriched_groups.setdefault(ntype, set()).add(name)

                        if extracted_groups:
                            st.markdown("**Extracted from Video**")
                            html = "".join(
                                pill(name, TYPE_COLORS.get(ntype, "#607D8B"))
                                for ntype in sorted(extracted_groups)
                                for name in sorted(extracted_groups[ntype])
                            )
                            st.markdown(html, unsafe_allow_html=True)

                        if enriched_groups:
                            st.markdown("**Enriched Knowledge**")
                            html = "".join(
                                pill(name, TYPE_COLORS.get(ntype, "#607D8B"))
                                for ntype in sorted(enriched_groups)
                                for name in sorted(enriched_groups[ntype])
                            )
                            st.markdown(html, unsafe_allow_html=True)

                        with st.expander(f"View {len(vid_nodes)} Relationships"):
                            rel_rows = []
                            for r in vid_nodes:
                                time_str = f"{r['time']:.1f}s" if r.get("time") else "—"
                                rel_rows.append({
                                    "From": f"{r['from_name']} ({r['from_type']})",
                                    "Relation": r["relation"],
                                    "To": f"{r['to_name']} ({r['to_type']})",
                                    "Timestamp": time_str,
                                })
                            st.dataframe(rel_rows, use_container_width=True, hide_index=True)

                    with st.expander(f"View {len(segs)} Transcript Segments"):
                        for seg in segs:
                            ts = int(seg["start_time"])
                            m_s, s_s = divmod(ts, 60)
                            text = seg["transcript"]
                            line = f"`{m_s}:{s_s:02d}`  {text}"
                            if seg.get("visual_text"):
                                line += f"  _(visual: {seg['visual_text'][:60]})_"
                            st.markdown(f"- {line}")

                    db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: Strategy Map
# ═══════════════════════════════════════════════════════════════════════════════
with tab_strategy:
    st.markdown("## 🗺 Strategy Map")
    st.caption(
        "Visualises every competency's strategies, their tactics, "
        "alternative approaches, prequels (what to learn first), and sequels (what comes next)."
    )

    STYPE_COLORS = {
        "Competency": "#2196F3",
        "Concept": "#4CAF50",
        "Strategy": "#FF5722",
        "Tactic": "#9C27B0",
        "Path": "#00BCD4",
        "Outcome": "#FF9800",
        "Personality": "#795548",
    }

    def tag(text, color, size="0.82em"):
        return (
            f"<span style='background:{color};color:white;padding:3px 10px;"
            f"border-radius:12px;font-size:{size};margin:2px;display:inline-block'>"
            f"{text}</span>"
        )

    db = Neo4jClient()
    if not db.driver:
        st.error("Neo4j not connected.")
    else:
        comp_query = """
        MATCH (c)-[:HAS_STRATEGY|HAS_ALTERNATIVE]->(:Strategy)
        WHERE c.name IS NOT NULL
        RETURN DISTINCT c.name AS name, labels(c)[0] AS label
        ORDER BY c.name
        """
        competencies = db.execute_read(comp_query) or []

        if not competencies:
            st.info("No strategy data yet. Ingest content via the Agent Chat tab.")
        else:
            for comp_rec in competencies:
                comp_name = comp_rec["name"]
                comp_label = comp_rec["label"] or "Competency"
                comp_color = STYPE_COLORS.get(comp_label, "#607D8B")

                with st.container(border=True):
                    st.markdown(
                        tag(comp_label.upper(), comp_color, "0.75em")
                        + f"&nbsp;<b style='font-size:1.1em'>{comp_name}</b>",
                        unsafe_allow_html=True,
                    )

                    # Prequels
                    prequel_q = """
                    MATCH (pre)-[:IS_PREQUEL_TO]->(c {name: $name})
                    RETURN collect(pre.name) AS prequels
                    """
                    preq_res = db.execute_read(prequel_q, {"name": comp_name}) or []
                    prequels = preq_res[0]["prequels"] if preq_res else []
                    if prequels:
                        preq_html = " ".join(tag(p, "#607D8B") for p in prequels)
                        st.markdown(
                            f"<small><b>Learn first:</b> {preq_html}</small>",
                            unsafe_allow_html=True,
                        )

                    # Outcomes
                    outcome_q = """
                    MATCH (c {name: $name})-[:LEADS_TO]->(o)
                    WHERE o.name IS NOT NULL
                    RETURN collect(o.name) AS outcomes
                    """
                    out_res = db.execute_read(outcome_q, {"name": comp_name}) or []
                    outcomes = out_res[0]["outcomes"] if out_res else []
                    if outcomes:
                        out_html = " ".join(
                            tag(o, STYPE_COLORS.get("Outcome", "#FF9800"))
                            for o in outcomes
                        )
                        st.markdown(
                            f"<small><b>Leads to:</b> {out_html}</small>",
                            unsafe_allow_html=True,
                        )

                    st.divider()

                    # Strategies
                    strat_q = """
                    MATCH (c {name: $comp})-[rel:HAS_STRATEGY|HAS_ALTERNATIVE]->(s:Strategy)
                    OPTIONAL MATCH (s)-[:HAS_TACTIC]->(t:Tactic)
                    OPTIONAL MATCH (s)-[:PRECEDED_BY]->(prereq)
                    RETURN s.name AS strategy,
                           type(rel) AS rel_type,
                           collect(DISTINCT t.name) AS tactics,
                           collect(DISTINCT prereq.name) AS strategy_prequels
                    ORDER BY rel_type
                    """
                    strat_rows = db.execute_read(strat_q, {"comp": comp_name}) or []

                    if strat_rows:
                        cols = st.columns(max(len(strat_rows), 1))
                        for col, row in zip(cols, strat_rows):
                            s_name = row["strategy"]
                            rel_type = row["rel_type"]
                            tactics = [t for t in row["tactics"] if t]
                            s_preqs = [p for p in row["strategy_prequels"] if p]
                            is_alt = rel_type == "HAS_ALTERNATIVE"
                            border_color = "#FF5722" if not is_alt else "#9E9E9E"
                            badge = "ALTERNATIVE" if is_alt else "STRATEGY"
                            badge_color = "#9E9E9E" if is_alt else "#FF5722"

                            with col:
                                st.markdown(
                                    f"<div style='border-left:4px solid {border_color};"
                                    f"padding:8px 12px;margin-bottom:6px'>"
                                    f"{tag(badge, badge_color, '0.7em')}"
                                    f"<br><b>{s_name}</b></div>",
                                    unsafe_allow_html=True,
                                )

                                if s_preqs:
                                    sp_html = " ".join(tag(p, "#607D8B") for p in s_preqs)
                                    st.markdown(
                                        f"<small>Requires: {sp_html}</small>",
                                        unsafe_allow_html=True,
                                    )

                                if tactics:
                                    st.markdown(
                                        tag("TACTICS", "#9C27B0", "0.7em"),
                                        unsafe_allow_html=True,
                                    )
                                    for tactic in tactics:
                                        tactic_detail_q = """
                                        MATCH (t:Tactic {name: $name})
                                        OPTIONAL MATCH (t)-[:REPLIES_TO]->(ctx)
                                        OPTIONAL MATCH (t)-[:INTENDS_TO]->(intent_node)
                                        OPTIONAL MATCH (t)-[:FOLLOWED_BY]->(nxt)
                                        RETURN t.difficulty   AS difficulty,
                                               t.applies_when AS applies_when,
                                               collect(DISTINCT ctx.name)[0] AS replies_to,
                                               collect(DISTINCT intent_node.name)[0] AS intends_to,
                                               collect(DISTINCT nxt.name)[0] AS sequel
                                        """
                                        td = (db.execute_read(tactic_detail_q, {"name": tactic}) or [{}])[0]

                                        DIFF_COLOR = {
                                            "Beginner": "#4CAF50",
                                            "Intermediate": "#FF9800",
                                            "Advanced": "#F44336",
                                        }
                                        diff_badge = (
                                            tag(difficulty, DIFF_COLOR.get(difficulty, "#607D8B"), "0.65em")
                                            if td.get("difficulty") else ""
                                        )

                                        card = (
                                            f"<div style='border:1px solid #e0e0e0;border-radius:8px;"
                                            f"padding:8px 10px;margin:5px 0;background:#fafafa'>"
                                            f"<b style='font-size:0.9em'>{tactic}</b> {diff_badge}<br>"
                                        )
                                        if td.get("replies_to"):
                                            card += f"<span style='font-size:0.78em;color:#555'><b>Replies to:</b> {td['replies_to']}</span><br>"
                                        if td.get("intends_to"):
                                            card += f"<span style='font-size:0.78em;color:#555'><b>Intent:</b> {td['intends_to']}</span><br>"
                                        if td.get("applies_when"):
                                            card += f"<span style='font-size:0.75em;color:#777;font-style:italic'>{td['applies_when']}</span><br>"
                                        if td.get("sequel"):
                                            card += f"<span style='font-size:0.75em;color:#9C27B0'>Next: {td['sequel']}</span>"
                                        card += "</div>"
                                        st.markdown(card, unsafe_allow_html=True)

                    # All relationships
                    all_rels_q = """
                    MATCH (c {name: $comp})-[r]-(other)
                    WHERE other.name IS NOT NULL
                    RETURN type(r) AS relation, other.name AS node,
                           labels(other)[0] AS node_type
                    ORDER BY type(r), other.name
                    """
                    all_rels = db.execute_read(all_rels_q, {"comp": comp_name}) or []
                    if all_rels:
                        with st.expander(f"All {len(all_rels)} relationships for {comp_name}"):
                            st.dataframe(
                                [{"Relation": r["relation"], "Node": r["node"], "Type": r["node_type"]} for r in all_rels],
                                use_container_width=True, hide_index=True,
                            )

    db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: Graph Search
# ═══════════════════════════════════════════════════════════════════════════════
with tab_search:
    st.markdown("## 🔍 Graph Search")
    st.caption("Search the Neo4j knowledge graph for concepts, competencies, and relationships.")

    query = st.text_input("Search for a concept (e.g., 'Conflict Resolution'):")

    if st.button("Search Knowledge Graph"):
        if query:
            db = Neo4jClient()
            st.info(f"Querying Neo4j Graph for **{query}**...")

            if db.driver:
                search_query = """
                MATCH (n)
                WHERE n.name CONTAINS $keyword OR labels(n)[0] CONTAINS $keyword
                MATCH (n)-[r]-(m)
                RETURN n.name as node, labels(n)[0] as type, r.source_time as time, m.name as related
                LIMIT 5
                """
                results = db.execute_read(search_query, {"keyword": query})

                if results:
                    st.success(f"Found {len(results)} matches!")
                    for res in results:
                        with st.expander(f"{res['node']} ({res['type']})"):
                            st.write(f"**Related to:** {res['related']}")
                            if res["time"]:
                                st.markdown(f"**Timestamp:** {res['time']:.2f}s")
                                st.markdown(
                                    f"[Jump to Video Position](https://youtube.com/watch?v=sample&t={int(res['time'])})"
                                )
                else:
                    st.warning("No matches found in the Knowledge Graph yet.")
            else:
                st.error("Neo4j not connected. Please start the database.")
            db.close()
        else:
            st.warning("Please enter a query.")

    st.divider()
    st.markdown("### Quick Entity Lookup")
    col1, col2 = st.columns([3, 1])
    with col1:
        entity_name = st.text_input("Entity name:", placeholder="e.g., Emotional Intelligence")
    with col2:
        if st.button("Lookup"):
            if entity_name:
                db = Neo4jClient()
                if db.driver:
                    node_q = """
                    MATCH (n {name: $name})
                    RETURN n.name AS name, labels(n)[0] AS type, properties(n) AS props
                    """
                    rel_q = """
                    MATCH (n {name: $name})-[r]-(m)
                    RETURN n.name AS subject, type(r) AS relation, m.name AS object,
                           labels(m)[0] AS obj_type, r.weight AS weight
                    LIMIT 20
                    """
                    node = db.execute_read(node_q, {"name": entity_name})
                    rels = db.execute_read(rel_q, {"name": entity_name})

                    if node:
                        st.success(f"**{node[0]['name']}** — Type: {node[0]['type']}")
                        if rels:
                            st.markdown("**Relationships:**")
                            st.dataframe(
                                [{
                                    "Subject": r["subject"],
                                    "Relation": r["relation"],
                                    "Object": r["object"],
                                    "Object Type": r["obj_type"],
                                    "Weight": r["weight"],
                                } for r in rels],
                                use_container_width=True, hide_index=True,
                            )
                    else:
                        st.warning(f"No entity named '{entity_name}' found.")
                db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: Live Audio
# ═══════════════════════════════════════════════════════════════════════════════
with tab_live:
    st.markdown("## 🎙 Live Audio Ingestion")
    st.caption(
        "Capture microphone audio and transcribe in real-time with Whisper. "
        "Transcriptions can be sent to the knowledge graph pipeline."
    )

    if IS_CLOUD:
        st.warning(
            "⚠️ Live audio recording requires a physical microphone and is not "
            "available on Streamlit Community Cloud. This feature works in "
            "your local environment."
        )
        st.info(
            "💡 **Local setup:** Clone the repository and run:\n\n"
            "```bash\n"
            "streamlit run app.py\n"
            "```\n\n"
            "Then upload audio files or use the Agent Chat tab to ingest content."
        )
        st.stop()

    CORPUS_PATH = "data/processed/corpus.json"
    REGISTRY_PATH = "data/processed/videos_registry.json"

    def _register_live_session(video_id, segments, label):
        import datetime as _dt
        segs = segments if isinstance(segments, list) else []
        duration = max((s.get("end", 0) or 0) for s in segs) - min((s.get("start", 0) or 0) for s in segs) if segs else 0
        registry = []
        if os.path.exists(REGISTRY_PATH):
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                registry = json.load(f)
        registry = [v for v in registry if v["video_id"] != video_id]
        registry.append({
            "video_id": video_id,
            "title": f"Live Audio ({label})",
            "url": "",
            "channel": "Live Mic",
            "thumbnail_url": "",
            "summary": f"Live microphone capture — {len(segs)} segments",
            "duration_sec": duration,
            "segment_count": len(segs),
            "ingested_at": _dt.datetime.utcnow().isoformat() + "Z",
        })
        os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4)

    if "live_ingestor" not in st.session_state:
        st.session_state.live_ingestor = None
        st.session_state.live_devices = list_audio_devices()
        st.session_state.live_is_recording = False
        st.session_state.live_is_streaming = False
        st.session_state.live_segments = []
        st.session_state.live_device_idx = 0
        st.session_state.live_device_sr = 16000
        st.session_state.live_wav_path = None
        st.session_state.live_video_id = None

    devices = st.session_state.live_devices
    if devices and "error" not in devices[0]:
        dev_options = {f"{d['name']} (ch:{d['channels']}, sr:{d['samplerate']})": d["index"] for d in devices}
        selected_dev_label = st.selectbox("Microphone", options=list(dev_options.keys()), index=0, key="live_dev_select")
        selected_idx = dev_options[selected_dev_label]
        st.session_state.live_device_idx = selected_idx
        for d in devices:
            if d["index"] == selected_idx:
                st.session_state.live_device_sr = d["samplerate"]
                break
    else:
        st.warning("No audio input devices found. Check microphone connections.")
        st.stop()

    mode = st.radio("Mode", ["Record & Transcribe", "Streaming"], horizontal=True)

    cols = st.columns([1, 1, 2])
    with cols[0]:
        record_btn = st.button(
            "⏺ Start" if not st.session_state.live_is_recording else "⏹ Stop",
            type="primary" if not st.session_state.live_is_recording else "secondary",
        )
    with cols[1]:
        stream_btn = st.button(
            "▶ Stream" if not st.session_state.live_is_streaming else "⏹ Stop Stream",
            type="primary" if not st.session_state.live_is_streaming else "secondary",
        )

    if st.session_state.live_is_recording:
        st.info("🔴 Recording… speak into the microphone.")
    elif st.session_state.live_is_streaming:
        st.info("🔵 Streaming… real-time transcription active.")
    elif st.session_state.live_segments:
        st.success(f"✅ {len(st.session_state.live_segments)} segment(s) captured.")
    else:
        st.info("Select a microphone and press Start to begin.")

    if record_btn:
        if not st.session_state.live_is_recording:
            ingestor = LiveAudioIngestor(
                device_index=selected_idx,
                samplerate=st.session_state.live_device_sr,
            )
            ingestor.start_recording()
            st.session_state.live_ingestor = ingestor
            st.session_state.live_is_recording = True
            st.session_state.live_is_streaming = False
            st.session_state.live_segments = []
            st.rerun()
        else:
            ingestor = st.session_state.live_ingestor
            if ingestor:
                audio, wav_path = ingestor.stop_recording(save=True)
                st.session_state.live_wav_path = wav_path
                st.session_state.live_is_recording = False
                if audio is not None:
                    with st.spinner("Transcribing with Whisper…"):
                        segments = ingestor.transcribe_file(wav_path)
                        st.session_state.live_segments = segments
                        vid_id, new_segs = ingestor.append_to_corpus(segments, CORPUS_PATH, source_label="live_record")
                        _register_live_session(vid_id, new_segs, "record")
                        st.session_state.live_video_id = vid_id
                st.session_state.live_ingestor = None
                st.rerun()

    if stream_btn:
        if not st.session_state.live_is_streaming:
            ingestor = LiveAudioIngestor(
                device_index=selected_idx,
                samplerate=st.session_state.live_device_sr,
            )
            st.session_state.live_ingestor = ingestor
            st.session_state.live_is_streaming = True
            st.session_state.live_is_recording = False
            st.session_state.live_segments = []

            collected_segments = []
            status_placeholder = st.empty()
            seg_placeholder = st.empty()

            def on_segment(new_segs):
                collected_segments.extend(new_segs)
                st.session_state.live_segments = collected_segments
                status_placeholder.info(f"🔵 Streaming… {len(collected_segments)} segments so far")
                with seg_placeholder.container():
                    for s in collected_segments[-5:]:
                        ts = int(s["start"])
                        m_s, s_s = divmod(ts, 60)
                        st.caption(f"`{m_s}:{s_s:02d}` {s['text'][:120]}")

            try:
                ingestor.transcribe_stream(window_sec=30, stride_sec=10, callback=on_segment)
            except Exception as e:
                st.error(f"Stream error: {e}")
            finally:
                st.session_state.live_is_streaming = False
                if collected_segments:
                    vid_id, new_segs = ingestor.append_to_corpus(collected_segments, CORPUS_PATH, source_label="live_stream")
                    _register_live_session(vid_id, new_segs, "stream")
                    st.session_state.live_video_id = vid_id
                st.session_state.live_ingestor = None
                st.rerun()
        else:
            ingestor = st.session_state.live_ingestor
            if ingestor:
                ingestor.stop_stream()
            st.session_state.live_is_streaming = False
            st.rerun()

    if st.session_state.live_segments:
        st.markdown("### Transcribed Segments")
        for seg in st.session_state.live_segments:
            ts = int(seg["start"])
            m_s, s_s = divmod(ts, 60)
            st.markdown(f"- `{m_s}:{s_s:02d}`  {seg['text']}")

        st.divider()
        if st.button("Send to Knowledge Graph Pipeline", type="primary"):
            db = Neo4jClient()
            if not db.driver:
                st.error("Neo4j not connected. Cannot build knowledge graph.")
            else:
                vid_id = st.session_state.live_video_id or "live_unknown"
                from src.core.extractor import SemanticEntityRecognizer
                from src.core.clustering import DependencyMiner
                from src.core.enrichment import GraphEnrichmentEngine

                extractor = SemanticEntityRecognizer()
                miner = DependencyMiner(db_client=db)

                total = len(st.session_state.live_segments)
                prog_bar = st.progress(0.0)
                status_text = st.empty()

                for idx, segment in enumerate(st.session_state.live_segments):
                    frac = (idx + 1) / max(total, 1)
                    prog_bar.progress(frac)
                    status_text.text(f"Extracting triplets — segment {idx + 1}/{total}…")
                    triplets = extractor.extract_triplets(segment["text"])
                    for t in triplets:
                        subject_name = extractor.map_to_dbpedia(t["subject"])
                        object_name = extractor.map_to_dbpedia(t["object"])
                        db.insert_triplet(
                            subject=subject_name, subject_type=t["subject_type"],
                            relation=t["relation"], obj=object_name, obj_type=t["object_type"],
                            source_time=segment["start"], video_id=vid_id,
                        )

                status_text.text("Mining prerequisites…")
                miner.determine_prerequisites(st.session_state.live_segments)
                miner.detect_learning_paths(st.session_state.live_segments)

                enrichment = GraphEnrichmentEngine(
                    db, progress_cb=lambda label: status_text.text(f"Running graph enrichment — {label}"),
                )
                enrichment.run_enrichment()

                prog_bar.progress(1.0)
                st.success(f"Knowledge graph updated from live audio! ({total} segments processed)")
            db.close()

        if st.session_state.live_wav_path and os.path.exists(st.session_state.live_wav_path):
            with open(st.session_state.live_wav_path, "rb") as f:
                st.download_button(
                    "Download WAV Recording",
                    data=f,
                    file_name=os.path.basename(st.session_state.live_wav_path),
                    mime="audio/wav",
                )

    st.divider()
    st.markdown("### Previously Ingested Live Audio Sessions")
    live_dir = "data/live_audio"
    if os.path.exists(live_dir):
        wav_files = sorted([f for f in os.listdir(live_dir) if f.endswith(".wav")], reverse=True)
        if wav_files:
            for wf in wav_files[:10]:
                wpath = os.path.join(live_dir, wf)
                size_mb = os.path.getsize(wpath) / (1024 * 1024)
                st.caption(f"📁 {wf}  ({size_mb:.1f} MB)")
        else:
            st.caption("No previous recordings.")
    else:
        st.caption("No previous recordings.")
