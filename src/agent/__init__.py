"""AIDE — Agentic Instructional Design Engine.

A multi-tool AI agent that ingests, queries, and enriches a leadership
knowledge graph stored in Neo4j.
"""

from src.agent.orchestrator import AIDESOrchestrator, Intent
from src.agent.memory import GraphMemory, ChatMemory
from src.agent.tools import IngestionTool, GraphQueryTool, BaseTool

__all__ = [
    "AIDESOrchestrator",
    "Intent",
    "GraphMemory",
    "ChatMemory",
    "IngestionTool",
    "GraphQueryTool",
    "BaseTool",
]