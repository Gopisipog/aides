"""In-memory conversation buffer for fast context retrieval.

Stores recent message history in a deque (ring buffer) so the agent
can quickly assemble context for LLM calls without hitting the database.
Automatically syncs with GraphMemory for persistence.
"""

from collections import deque
from typing import Any, Dict, List, Optional
from uuid import uuid4


class ChatMemory:
    """Lightweight, fast conversation memory.

    Maintains a ring buffer of recent messages for quick context assembly.
    Optionally backed by GraphMemory for persistence to Neo4j.

    Usage:
        memory = ChatMemory(max_turns=50)
        memory.add_message("user", "What is leadership?")
        memory.add_message("assistant", "Leadership is influence.")
        context = memory.get_context()  # Formatted for LLM
    """

    def __init__(self, max_turns: int = 50, persist: bool = False):
        """Initialize the buffer.

        Args:
            max_turns: Max number of messages to keep in buffer (oldest dropped).
            persist: If True, sync to GraphMemory when add_message is called.
                     Requires graph_memory and session_id to be set.
        """
        self._buffer: deque = deque(maxlen=max_turns)
        self._max_turns = max_turns
        self._persist = persist
        self._graph_memory = None
        self._session_id = None

    def bind_graph_memory(self, graph_memory, session_id: str):
        """Link to persistent graph memory for sync."""
        self._graph_memory = graph_memory
        self._session_id = session_id

    def add_message(
        self,
        role: str,
        message: str,
        related_entities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a message to the buffer and optionally persist to graph.

        Args:
            role: 'user', 'assistant', or 'system'
            message: The message text
            related_entities: Optional entity names referenced
            metadata: Optional metadata dict

        Returns:
            Generated message_id
        """
        message_id = str(uuid4())

        entry = {
            "message_id": message_id,
            "role": role,
            "message": message,
            "related_entities": related_entities or [],
            "metadata": metadata or {},
        }
        self._buffer.append(entry)

        # Optionally persist to graph database
        if self._persist and self._graph_memory and self._session_id:
            self._graph_memory.store_message(
                session_id=self._session_id,
                role=role,
                message=message,
                related_entities=related_entities,
                metadata=metadata,
            )

        return message_id

    def get_context(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Get formatted conversation context for injection into an LLM prompt.

        Returns a list of dicts with 'role' and 'content' keys (OpenAI/Anthropic format).
        If limit is provided, returns only the most recent N messages.

        Example:
            [
                {"role": "system", "content": "You are a leadership coach..."},
                {"role": "user", "content": "What is leadership?"},
                {"role": "assistant", "content": "Leadership is influence."},
            ]
        """
        entries = list(self._buffer)
        if limit:
            entries = entries[-limit:]

        return [
            {"role": e["role"], "content": e["message"]}
            for e in entries
        ]

    def get_last_user_message(self) -> Optional[str]:
        """Get the most recent user message."""
        for entry in reversed(self._buffer):
            if entry["role"] == "user":
                return entry["message"]
        return None

    def get_last_assistant_message(self) -> Optional[str]:
        """Get the most recent assistant message."""
        for entry in reversed(self._buffer):
            if entry["role"] == "assistant":
                return entry["message"]
        return None

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search the in-memory buffer for messages containing query text."""
        return [
            e for e in self._buffer
            if query.lower() in e["message"].lower()
        ]

    def clear(self):
        """Clear the buffer (does not affect persistent storage)."""
        self._buffer.clear()

    @property
    def turn_count(self) -> int:
        """Number of message pairs (user+assistant) in buffer."""
        return len(self._buffer) // 2

    @property
    def message_count(self) -> int:
        return len(self._buffer)

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Export buffer as raw dict list."""
        return list(self._buffer)