# 🧠 AIDE — Agentic Instructional Design Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Neo4j](https://img.shields.io/badge/database-Neo4j-4581C3.svg)](https://neo4j.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An **intelligent AI agent** that ingests, queries, enriches, and teaches from a leadership knowledge graph. Built on top of the V-LKG (Video Leadership Knowledge Graph) multimodal pipeline, AIDE transforms unstructured leadership content (YouTube videos, live audio, text) into a structured, queryable knowledge base, then provides an interactive conversational interface for learning and exploration.

---

## ✨ Features

### 🤖 AI Agent Chat
- **Intent-aware routing** — The agent automatically detects whether you want to ingest content, search the graph, run enrichment, or have a general leadership conversation
- **ReAct-style orchestration** — Reasoning + Acting loop with tool dispatch
- **Persistent memory** — Conversations are stored in Neo4j, enabling follow-up questions that reference prior context
- **Graph-grounded responses** — The agent queries Neo4j to ground its answers in actual ingested knowledge

### 📥 Ingestion Pipeline
- **YouTube videos** — Download, transcribe (Whisper), extract knowledge triplets via LLM, insert into Neo4j
- **Live audio** — Record from microphone, transcribe in real-time, extract knowledge
- **Free text** — Paste any article, notes, or content for triplet extraction

### 🔍 Knowledge Graph Querying
- **Entity lookup** — Find any concept, competency, strategy, or tactic by name
- **Relationship traversal** — See what's connected to what, with weights and types
- **Semantic search** — Keyword matching over node names
- **Graph statistics** — Node counts, relationship counts, degree distribution

### 🧠 Graph Enrichment (Phases A–F)
| Phase | Description |
|---|---|
| **A** | Bridge isolated nodes to core concepts (Brain Balance, Innate Wisdom) |
| **B** | Generate strategies and tactics for competencies without them |
| **C** | Add alternative approaches and cross-references |
| **D** | Discover learning paths (chains of highly-similar segments) |
| **E** | Detect prerequisites between concepts |
| **F** | Compute centrality and suggest connections |

### 🎓 Proactive Learning
- **Cross-video insights** — Connects concepts across multiple ingested videos
- **Reflective questions** — Generates personalized questions based on graph content
- **Action items** — Creates actionable follow-ups from conversation history

---

## 🏗 Architecture

```
User Query / YouTube Video / Live Audio / Text
          │
          ▼
┌──────────────────────────────────────────┐
│            INGESTION LAYER               │
│  YouTubeDownloader │ LiveAudioIngestor   │
│  MultimodalProcessor (Whisper + OCR)     │
└──────────────────┬───────────────────────┘
                   ▼
┌──────────────────────────────────────────┐
│         AGENT ORCHESTRATOR               │
│  ┌────────────────────────────────────┐  │
│  │  AIDESOrchestrator                 │  │
│  │  ├─ Intent Classification (LLM)    │  │
│  │  ├─ Tool Dispatch                  │  │
│  │  ├─ Memory (GraphMemory + Chat)    │  │
│  │  └─ Response Generation            │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  Tools                             │  │
│  │  ├─ IngestionTool                  │  │
│  │  ├─ GraphQueryTool                 │  │
│  │  ├─ GraphEnrichmentEngine          │  │
│  │  └─ ProactiveLearningEngine        │  │
│  └────────────────────────────────────┘  │
└──────────────────┬───────────────────────┘
                   ▼
┌──────────────────────────────────────────┐
│        MEMORY & KNOWLEDGE LAYER          │
│  ┌───────────┐  ┌───────────┐  ┌──────┐ │
│  │   Neo4j   │  │  Corpus   │  │Video │ │
│  │ Graph DB  │  │   JSON    │  │Registry││
│  └───────────┘  └───────────┘  └──────┘ │
└──────────────────┬───────────────────────┘
                   ▼
┌──────────────────────────────────────────┐
│           INTERFACE LAYER                │
│  Streamlit Web UI  │  Desktop Tray App   │
│  CLI (interactive) │  Single Query Mode  │
└──────────────────────────────────────────┘
```

### Directory Structure

```
aides/
├── app.py                     # Streamlit agent chat UI
├── main.py                    # CLI entry point (agent + legacy pipeline)
├── src/
│   ├── agent/                 # ★ NEW: AI Agent Framework ★
│   │   ├── orchestrator.py    #   ReAct-style agent loop
│   │   ├── tools/
│   │   │   ├── base.py        #   Base tool class
│   │   │   ├── ingestion_tool.py  #   YouTube/live/text ingestion
│   │   │   └── graph_query_tool.py #   Neo4j querying
│   │   └── memory/
│   │       ├── graph_memory.py    #   Neo4j-based conversation persistence
│   │       └── chat_memory.py     #   In-memory ring buffer
│   ├── core/                  # Existing core pipeline
│   │   ├── extractor.py       #   LLM triplet extraction
│   │   ├── clustering.py      #   Dependency mining + path detection
│   │   ├── enrichment.py      #   Graph enrichment (Phases A-F)
│   │   └── proactive.py       #   Proactive learning engine
│   ├── database/
│   │   ├── neo4j_client.py    #   Neo4j graph database client
│   │   └── schema.py          #   Schema constraints
│   └── ingestion/
│       ├── downloader.py      #   YouTube downloading (yt-dlp)
│       ├── processor.py       #   Whisper transcription + OCR
│       └── live_audio.py      #   Microphone capture + streaming
├── data/
│   ├── processed/             # Corpus JSON, video registry, insights
│   ├── raw/                   # Raw video/audio files
│   └── live_audio/            # Captured microphone recordings
└── vlkg_desktop/              # Desktop tray application
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Neo4j** — Local instance (Docker) or [Neo4j AuraDB](https://console.neo4j.io/) (free cloud tier)
- **API Key** — DeepSeek (recommended) or OpenAI for LLM features

### Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd aides

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment
# Edit .env with your API keys and Neo4j credentials
```

### Quick Start — Agent Chat (Streamlit)

```bash
streamlit run app.py
```

Opens a web interface with the **Agent Chat** tab as the primary entry point.

### Quick Start — Interactive CLI Agent

```bash
python main.py --agent
```

### Quick Start — Single Query

```bash
python main.py --query "Search for emotional intelligence"
python main.py --query "Show me graph statistics"
python main.py --query "Ingest this YouTube video: https://youtube.com/watch?v=..."
```

### Legacy Pipeline (Direct)

```bash
# Process a YouTube video
python main.py --url "https://youtube.com/watch?v=..."

# Record and process live audio
python main.py --live --duration 60
```

---

## 💬 Example Agent Interactions

| You Say | AIDE Does |
|---|---|
| "Ingest this YouTube video: https://youtube.com/watch?v=jfW6gL6hKhk" | Downloads, transcribes, extracts triplets, mines dependencies, enriches graph |
| "Search for emotional intelligence" | Queries Neo4j for matching nodes |
| "Tell me about servant leadership" | Looks up entity + relationships in graph |
| "Enrich the knowledge graph" | Runs enrichment phases A–F |
| "Show me graph statistics" | Returns node/edge counts, type distribution |
| "What is the difference between strategy and tactic?" | Generates an LLM response grounded in graph knowledge |
| "Generate questions about this content" | Proactive learning engine creates reflective questions |

---

## 🛠 Technologies Used

| Technology | Purpose |
|---|---|
| **Python 3.10+** | Core language |
| **Neo4j** (Local or AuraDB Cloud) | Persistent knowledge graph database |
| **Whisper** (openai-whisper) | Local audio transcription |
| **DeepSeek / OpenAI API** | LLM for triplet extraction, enrichment, agent reasoning |
| **Sentence-Transformers** (all-MiniLM-L6-v2) | Cosine similarity for dependency mining |
| **Streamlit** | Web UI for agent chat and knowledge browsing |
| **yt-dlp** | YouTube video downloading |
| **EasyOCR** | Optional video OCR for visual text extraction |
| **sounddevice / soundfile** | Microphone capture and WAV I/O |
| **static-ffmpeg** | Bundled ffmpeg for audio processing |

---

## 🤝 Third-Party Integrations

| Integration | Authorization |
|---|---|
| YouTube (via yt-dlp) | Public (no API key needed) |
| DeepSeek API | `DEEPSEEK_API_KEY` in `.env` |
| OpenAI API | `OPENAI_API_KEY` in `.env` |
| Neo4j (Local or AuraDB) | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` in `.env` |
| Whisper (OpenAI) | Open-source (MIT license) |
| Sentence-Transformers | Open-source (Apache 2.0) |

---

## 📁 Data Sources

| Source | Method | Type |
|---|---|---|
| YouTube videos | `yt-dlp` + Whisper | Audio → Text → Triplets |
| Live microphone | `sounddevice` + Whisper | Audio → Text → Triplets |
| Text / Articles | Direct LLM extraction | Text → Triplets |
| Video OCR (optional) | EasyOCR | Visual text → Triplets |

---

## 🔧 Development

### Adding a New Tool

1. Create a new file in `src/agent/tools/` extending `BaseTool`
2. Implement the `run()` method returning `{status, message, ...}`
3. Register it in `tools/__init__.py`
4. Add a case in `AIDESOrchestrator.dispatch_tool()` or let the agent discover it

### Adding a New Intent

1. Add a new `Intent` enum value in `orchestrator.py`
2. Add a detection pattern in `INTENT_PATTERNS`
3. Add extraction logic in `_extract_params()`
4. Add dispatch logic in `dispatch_tool()`

---

## 📊 Graph Schema

### Node Types
- **Competency** — A learnable leadership skill (e.g., Active Listening)
- **Concept** — An abstract idea (e.g., Psychological Safety)
- **Strategy** — A high-level approach (e.g., Servant Leadership)
- **Tactic** — A specific practice (e.g., Daily Stand-up)
- **Path** — Ordered learning journey
- **Outcome** — Measurable result
- **Personality** — Trait or style
- **Conversation** — Agent chat messages
- **Session** — User conversation sessions

### Relationship Types
- `DEVELOPS_SKILL`, `IS_EXAMPLE_OF`, `SEMANTICALLY_RELATED`
- `HAS_STRATEGY`, `HAS_TACTIC`, `HAS_ALTERNATIVE`
- `LEADS_TO`, `ENABLES`, `REQUIRES`
- `IS_PREREQUISITE_FOR`, `IS_PART_OF`
- `HAS_MESSAGE`, `NEXT_MESSAGE`, `REFERENCES`
- `IS_PREQUEL_TO`, `PRECEDED_BY`, `FOLLOWED_BY`
- `REPLIES_TO`, `INTENDS_TO`

---

## 📝 License

This project is open source under the MIT License.

---

## ☁️ Deploy to Streamlit Community Cloud

Deploy AIDE as a public web app with zero server management.

### Step 1: Prerequisites

| Requirement | Details |
|---|---|
| **GitHub account** | [github.com](https://github.com) — to host the repository |
| **Neo4j AuraDB** | [console.neo4j.io](https://console.neo4j.io) — free tier (50k nodes) |
| **DeepSeek API key** | [platform.deepseek.com](https://platform.deepseek.com) — primary LLM |
| **Streamlit Cloud account** | [share.streamlit.io](https://share.streamlit.io) — free tier included with GitHub |

### Step 2: Push the code to GitHub

```bash
# Inside the project directory
git init
git add .
git commit -m "Initial commit: AIDE Agent"
git remote add origin https://github.com/YOUR_USERNAME/aides.git
git push -u origin main
```

> ⚠️ **Important:** Ensure `.env` and `.streamlit/secrets.toml` are in `.gitignore` so API keys are NOT committed.

### Step 3: Configure Neo4j AuraDB (Cloud Graph Database)

1. Go to [console.neo4j.io](https://console.neo4j.io) and sign up
2. Create a **free AuraDB Professional** instance
3. Wait ~2 minutes for provisioning
4. Copy the **Connection URI** (looks like `bolt+s://xxxxxxxx.databases.neo4j.io:7687`)
5. Copy the **auto-generated password**

### Step 4: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"** → Select your GitHub repo → Branch: `main` → File: `app.py`
3. Click **"Advanced settings..."** → **"Secrets"**
4. Paste the following (replace with your actual credentials):

```toml
# ── API Keys ─────────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = "sk-your-deepseek-key"
OPENAI_API_KEY = "sk-your-openai-key"       # Optional fallback

# ── Neo4j AuraDB ─────────────────────────────────────────────────────────────
NEO4J_URI = "bolt+s://xxxxxxxx.databases.neo4j.io:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your-aura-password"
```

5. Click **"Deploy"** and wait ~3–5 minutes for the build

### Step 5: Verify the deployment

Your app will be live at: `https://YOUR_USERNAME-aides-app-XXXXXX.streamlit.app`

The app will automatically:
- Detect that it's running in the cloud (`IS_CLOUD = True`)
- Disable local-only features (live microphone, streaming audio)
- Use secrets from Streamlit's UI (not `.env`)
- Connect to Neo4j AuraDB via the secrets

### Cloud Limitations

| Feature | Local | Cloud |
|---|---|---|
| YouTube ingestion | ✅ | ✅ |
| Text ingestion | ✅ | ✅ |
| Graph querying | ✅ | ✅ |
| Graph enrichment | ✅ | ✅ |
| Agent chat | ✅ | ✅ |
| Live microphone recording | ✅ | ❌ (no hardware access) |
| Live streaming transcription | ✅ | ❌ (no hardware access) |
| Video OCR (EasyOCR) | ⚠️ Optional | ❌ (no GPU) |

### Troubleshooting

| Issue | Solution |
|---|---|
| **Build fails with ffmpeg error** | Ensure `packages.txt` contains `ffmpeg` at the repo root |
| **Neo4j connection fails** | Verify secrets are set correctly in Streamlit Cloud Settings → Secrets |
| **"No Neo4j connection" in UI** | Check that your AuraDB instance is in the **running** state (not paused) |
| **API key errors** | Ensure `DEEPSEEK_API_KEY` is set in secrets, not just in `.env` |
| **Large file downloads time out** | Streamlit Cloud has a 500 MB ephemeral disk. For large videos, process locally and push the corpus |

---

## 🙏 Acknowledgments

Built on the foundation of the V-LKG (Video Leadership Knowledge Graph) project, originally designed for multimodal knowledge graph construction from YouTube leadership content. Repurposed into a general-purpose AI agent framework with persistent memory and conversational intelligence.
