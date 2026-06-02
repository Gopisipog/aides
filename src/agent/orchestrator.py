"""AI Agent Orchestrator — the main reasoning engine that routes user intents to tools.

Uses a ReAct-style loop (Reasoning + Acting) to:
1. Classify user intent
2. Dispatch to the appropriate tool
3. Maintain conversational context via memory
4. Return a structured response
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from src.agent.tools import IngestionTool, GraphQueryTool
from src.agent.memory import GraphMemory, ChatMemory
from src.core.proactive import ProactiveLearningEngine
from src.core.enrichment import GraphEnrichmentEngine
from src.database.neo4j_client import Neo4jClient
from src.database.schema import Neo4jSchemaManager


class Intent(Enum):
    """Supported user intents the orchestrator can handle."""

    INGEST_YOUTUBE = "ingest_youtube"
    INGEST_LIVE = "ingest_live"
    INGEST_TEXT = "ingest_text"
    QUERY_GRAPH = "query_graph"
    ENRICH_GRAPH = "enrich_graph"
    CHAT = "chat"
    STATS = "stats"
    HELP = "help"
    UNKNOWN = "unknown"


# Intent detection patterns (regex on user input)
INTENT_PATTERNS: List[Tuple[Intent, str]] = [
    (Intent.INGEST_YOUTUBE, r"(?:ingest|process|add|import|load)\s+(?:youtube|video|url)\s*(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)"),
    (Intent.INGEST_YOUTUBE, r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)\S+"),
    (Intent.INGEST_LIVE, r"(?:record|live|mic|microphone|start recording)"),
    (Intent.INGEST_TEXT, r"(?:ingest|process|learn)\s+this\s+(?:text|article|content|passage)"),
    (Intent.ENRICH_GRAPH, r"(?:enrich|enhance|expand|improve|complete)\s+(?:graph|knowledge|enrichment)"),
    (Intent.STATS, r"(?:stats|statistics|count|how many|summary of graph|graph status)"),
    (Intent.HELP, r"^(?:help|\?|what can you do|commands|capabilities)$"),
    (Intent.QUERY_GRAPH, r"(?:search|find|lookup|query|what is|tell me about|show me|related to)"),
]

# Give the "CHAT" intent lowest priority — match it last
INTENT_PATTERNS.append((Intent.CHAT, r".*"))  # fallback


class AIDESOrchestrator:
    """Main agent orchestrator.

    Routes user input to tools, maintains conversation state,
    and returns structured responses.
    """

    def __init__(self, use_persistence: bool = True, auto_enrich: bool = True):
        """Initialize the agent.

        Args:
            use_persistence: Whether to persist conversations to Neo4j.
            auto_enrich: Whether to run graph enrichment automatically after ingestion.
        """
        self._auto_enrich = auto_enrich
        self._use_persistence = use_persistence

        # Tools
        self.ingestion_tool = IngestionTool(run_enrichment=auto_enrich)
        self.query_tool = GraphQueryTool()

        # Memory
        self.chat_memory = ChatMemory(max_turns=100, persist=use_persistence)

        if use_persistence:
            self.graph_memory = GraphMemory()
            self._session_id = self.graph_memory.create_session()
            self.chat_memory.bind_graph_memory(self.graph_memory, self._session_id)
        else:
            self.graph_memory = None
            self._session_id = "in_memory"

        # Proactive learning engine (for chat/QA)
        self.proactive_engine = ProactiveLearningEngine()

        # System prompt
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the system prompt that defines agent behavior."""
        return f"""You are AIDE (Agentic Instructional Design Engine), an intelligent assistant
specializing in leadership knowledge management. You help users:

1. **Ingest** YouTube videos, live audio, or text into a knowledge graph.
2. **Query** the knowledge graph to find concepts, relationships, and learning paths.
3. **Enrich** the graph with strategies, tactics, prerequisites, and learning paths.
4. **Learn proactively** — generate questions, action items, and cross-video insights.

You have access to these tools (I will call them on your behalf):
- `IngestionTool` — ingests YouTube URL, live audio, or text
- `GraphQueryTool` — searches/looks up entities, relationships, graph stats
- `GraphEnrichmentEngine` — runs enrichment phases A-F
- `ProactiveLearningEngine` — generates questions, cross-video patterns, action items

Your session ID is: {self._session_id}

Be concise, helpful, and pedagogical. Use the knowledge graph to ground your responses.
When you don't know something, use the graph query tool rather than guessing.
"""

    @property
    def session_id(self) -> str:
        return self._session_id

    # ── Intent Detection ─────────────────────────────────────────────────────

    def classify_intent(self, user_input: str) -> Tuple[Intent, Dict[str, Any]]:
        """Detect user intent from the input text.

        Returns:
            Tuple of (Intent, extracted_params dict).
        """
        text = user_input.strip().lower()

        # Try LLM-based classification first for ambiguous queries
        if len(text) > 20:
            llm_intent = self._llm_classify_intent(user_input)
            if llm_intent:
                return llm_intent

        # Fallback: regex pattern matching
        for intent, pattern in INTENT_PATTERNS:
            if intent == Intent.CHAT:
                continue  # skip fallback for now
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return intent, self._extract_params(intent, user_input, match)

        # Default to CHAT
        return Intent.CHAT, {"query": user_input}

    def _llm_classify_intent(self, user_input: str) -> Optional[Tuple[Intent, Dict[str, Any]]]:
        """Use a lightweight LLM call to classify ambiguous intents."""
        from openai import OpenAI

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            return None

        try:
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            prompt = f"""Classify the user intent to ONE of these categories. Reply with ONLY the category name.

Categories:
- INGEST_YOUTUBE: User wants to ingest/process a YouTube URL or video
- INGEST_LIVE: User wants to record live audio from microphone
- INGEST_TEXT: User wants to ingest raw text or content
- QUERY_GRAPH: User wants to search/find/query the knowledge graph
- ENRICH_GRAPH: User wants to expand or enrich the knowledge graph
- STATS: User wants graph statistics or counts
- CHAT: General conversation, questions about leadership, asking for advice
- HELP: User asks what the agent can do

User: "{user_input}"
Category:"""
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=20,
            )
            category = resp.choices[0].message.content.strip()
            intent = Intent(category.lower())
            return intent, self._extract_params(intent, user_input, None)
        except Exception:
            return None

    def _extract_params(self, intent: Intent, user_input: str, match: Optional[re.Match]) -> Dict[str, Any]:
        """Extract parameters from the user input based on detected intent."""
        params = {"original_input": user_input}

        if intent == Intent.INGEST_YOUTUBE:
            # Extract URL
            url_match = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)\S+", user_input)
            if url_match:
                params["url"] = url_match.group(0)
            else:
                params["url"] = user_input  # Might be just a title; let tool handle it

        elif intent == Intent.INGEST_LIVE:
            dur_match = re.search(r"(\d+)\s*(?:second|sec|s)", user_input, re.IGNORECASE)
            params["duration_sec"] = int(dur_match.group(1)) if dur_match else 60

        elif intent == Intent.INGEST_TEXT:
            # For text ingestion, take the full input as the text
            params["text"] = user_input

        elif intent == Intent.QUERY_GRAPH:
            # Extract the query after keywords
            for prefix in ["search for", "find", "lookup", "tell me about", "show me", "what is", "related to"]:
                if prefix in user_input.lower():
                    query_part = user_input.lower().split(prefix, 1)[-1].strip()
                    if query_part:
                        params["query"] = query_part
                        break
            if "query" not in params:
                params["query"] = user_input

        elif intent == Intent.STATS:
            params["action"] = "stats"

        return params

    # ── Tool Dispatch ────────────────────────────────────────────────────────

    def dispatch_tool(self, intent: Intent, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the appropriate tool for the given intent and parameters.

        Returns:
            Dict with status, message, and optional result data.
        """
        if intent == Intent.INGEST_YOUTUBE:
            url = params.get("url", "")
            return self.ingestion_tool.run(source_type="youtube", url=url)

        elif intent == Intent.INGEST_LIVE:
            duration = params.get("duration_sec", 60)
            return self.ingestion_tool.run(source_type="live_audio", duration_sec=duration)

        elif intent == Intent.INGEST_TEXT:
            text = params.get("text", params.get("original_input", ""))
            return self.ingestion_tool.run(source_type="text", transcript_text=text)

        elif intent == Intent.QUERY_GRAPH:
            query = params.get("query", "")
            if not query or query == params.get("original_input", ""):
                # Just a general search
                return self.query_tool.run(query_type="search", keyword=query, limit=10)
            # Try entity lookup first
            entity_result = self.query_tool.run(query_type="entity", entity_name=query)
            if entity_result.get("found"):
                return entity_result
            # Fallback to search
            return self.query_tool.run(query_type="search", keyword=query, limit=10)

        elif intent == Intent.ENRICH_GRAPH:
            db = Neo4jClient()
            engine = GraphEnrichmentEngine(db)
            engine.run_enrichment()
            db.close()
            return {
                "status": "success",
                "message": "Graph enrichment phases (A-F) completed successfully. "
                           "New strategies, tactics, paths, and relationships have been added."
            }

        elif intent == Intent.STATS:
            return self.query_tool.run(query_type="stats")

        elif intent == Intent.HELP:
            return self._get_help_message()

        else:
            return {"status": "info", "message": "I'll handle this as a general conversation.", "intent": "chat"}

    def _get_help_message(self) -> Dict[str, Any]:
        return {
            "status": "success",
            "message": """Here's what I can do:

📥 **Ingest Content**
- **YouTube**: Paste a YouTube URL to ingest a leadership video
- **Live Audio**: Say "record for 60 seconds" to record from your microphone
- **Text**: Feed me raw text to extract knowledge from

🔍 **Query the Graph**
- "Search for emotional intelligence" — find concepts
- "Tell me about active listening" — entity details
- "Show me related to conflict resolution" — relationship traversal
- "Graph statistics" — node/edge counts

🧠 **Enrich the Graph**
- "Enrich the graph" — runs automated enrichment (strategies, tactics, learning paths)

💬 **Proactive Learning**
- Ask any leadership question for personalized coaching
- "Generate questions about this video"
- "Create action items based on what I learned"

Just tell me what you'd like to do!"""
        }

    # ── Proactive Chat (General Conversation) ────────────────────────────────

    def _handle_chat(self, user_input: str) -> Dict[str, Any]:
        """Handle general conversation using the LLM with graph context."""
        from openai import OpenAI

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            return {
                "status": "success",
                "message": "I'm in offline mode. Please set your DEEPSEEK_API_KEY for full conversational ability."
            }

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        # Get conversation history from memory
        chat_context = self.chat_memory.get_context(limit=10)

        # Try to get some graph context for grounding
        graph_context = self._get_graph_context_for_question(user_input)

        # Build messages
        messages = [{"role": "system", "content": self._system_prompt}]

        # Inject graph context if available
        if graph_context:
            messages.append({
                "role": "system",
                "content": f"Relevant knowledge graph context:\n{json.dumps(graph_context, indent=2)}"
            })

        # Add conversation history
        messages.extend(chat_context)

        # Add current user message
        messages.append({"role": "user", "content": user_input})

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            reply = resp.choices[0].message.content.strip()
        except Exception as e:
            reply = f"Sorry, I encountered an error generating a response: {e}"

        return {"status": "success", "message": reply, "source": "llm"}

    def _get_graph_context_for_question(self, question: str) -> Optional[Dict[str, Any]]:
        """Try to find relevant graph entities for a user question."""
        if not self.query_tool.db.driver:
            return None

        # Extract potential keywords from question
        keywords = [w for w in re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question)
                    if len(w) > 3]
        if not keywords:
            # Use the first few meaningful words
            words = [w for w in question.lower().split() if len(w) > 4]
            keywords = words[:3]

        context = {}
        for kw in keywords[:3]:
            result = self.query_tool.run(query_type="search", keyword=kw, limit=3)
            if result.get("results"):
                context[kw] = result["results"]

        return context if context else None

    # ── Main Entry Point ─────────────────────────────────────────────────────

    def process(self, user_input: str) -> Dict[str, Any]:
        """Process a user input and return a response.

        This is the main entry point for the agent.

        Args:
            user_input: The raw user message.

        Returns:
            Dict with keys: status, message, intent, (optional) result_data
        """
        # 1. Classify intent
        intent, params = self.classify_intent(user_input)

        # 2. Store user message in memory
        self.chat_memory.add_message("user", user_input)

        # 3. Dispatch to appropriate handler
        if intent == Intent.CHAT or intent == Intent.UNKNOWN:
            result = self._handle_chat(user_input)
        else:
            result = self.dispatch_tool(intent, params)

        # 4. Store assistant response in memory
        response_text = result.get("message", result.get("result", str(result)))
        self.chat_memory.add_message(
            "assistant",
            response_text,
            metadata={"intent": intent.value, "status": result.get("status", "info")}
        )

        # 5. Return structured result
        return {
            "status": result.get("status", "success"),
            "message": response_text,
            "intent": intent.value,
            "data": result.get("result") or result.get("stats") or result.get("results"),
        }

    def close(self):
        """Clean up resources."""
        if self.graph_memory:
            self.graph_memory.close()
        self.ingestion_tool = None
        self.query_tool = None