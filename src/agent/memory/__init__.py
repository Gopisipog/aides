"""Memory module for the AI agent.

Stores conversation history and user context. Can be backed by:
- Neo4j (knowledge graph persistence)
- In-memory buffer (recent conversation turns)
- Future: SQLite file for portable conversation logs
"""

from src.agent.memory.graph_memory import GraphMemory
from src.agent.memory.chat_memory import ChatMemory

__all__ = ["GraphMemory", "ChatMemory"]