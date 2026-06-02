"""Persistent agent memory stored in the Neo4j knowledge graph.

Stores conversations as nodes linked to relevant concepts/competencies,
enabling context-aware follow-up questions and personalized learning paths.
"""

import json
import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.database.neo4j_client import Neo4jClient


class GraphMemory:
    """Agent memory backed by Neo4j.

    Each user session is a chain of Conversation nodes connected via
    :NEXT_MESSAGE relationships. Messages can also link to relevant
    graph entities (Concept, Competency, Strategy, etc.) via :REFERENCES edges.
    """

    def __init__(self, db: Optional[Neo4jClient] = None):
        self.db = db or Neo4jClient()
        self._setup_schema()

    def _setup_schema(self):
        """Ensure conversation schema constraints exist."""
        if not self.db.driver:
            print("Warning: No Neo4j connection for memory.")
            return
        try:
            # Create constraints if not already present
            self.db.execute_write(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Conversation) REQUIRE c.message_id IS UNIQUE"
            )
            self.db.execute_write(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Session) REQUIRE s.session_id IS UNIQUE"
            )
        except Exception as e:
            print(f"Memory schema setup warning: {e}")

    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new conversation session.

        Args:
            session_id: Optional custom ID. Auto-generated UUID if omitted.

        Returns:
            The session ID string.
        """
        sid = session_id or str(uuid4())
        if self.db.driver:
            try:
                self.db.execute_write(
                    "MERGE (s:Session {session_id: $sid}) "
                    "ON CREATE SET s.created_at = $now, s.message_count = 0",
                    {"sid": sid, "now": datetime.datetime.utcnow().isoformat() + "Z"}
                )
            except Exception as e:
                print(f"Session creation error: {e}")
        return sid

    def store_message(
        self,
        session_id: str,
        role: str,
        message: str,
        related_entities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a user or assistant message in the graph.

        Args:
            session_id: Active session ID.
            role: 'user' or 'assistant'.
            message: The message text.
            related_entities: Optional list of entity names this message references.
            metadata: Optional dict with tool calls, confidence, etc.

        Returns:
            The generated message_id.
        """
        if not self.db.driver:
            return ""

        message_id = str(uuid4())
        now = datetime.datetime.utcnow().isoformat() + "Z"

        try:
            # Create the message node
            self.db.execute_write(
                """MERGE (m:Conversation {message_id: $mid})
                   SET m.role = $role, m.message = $msg,
                       m.timestamp = $ts, m.session_id = $sid,
                       m.metadata = $meta""",
                {
                    "mid": message_id,
                    "role": role,
                    "msg": message,
                    "ts": now,
                    "sid": session_id,
                    "meta": json.dumps(metadata or {}),
                }
            )

            # Link to session
            self.db.execute_write(
                """MATCH (s:Session {session_id: $sid})
                   MATCH (m:Conversation {message_id: $mid})
                   MERGE (s)-[r:HAS_MESSAGE]->(m)
                   ON CREATE SET s.message_count = coalesce(s.message_count, 0) + 1""",
                {"sid": session_id, "mid": message_id}
            )

            # Link to previous message in session (for conversation ordering)
            self.db.execute_write(
                """MATCH (s:Session {session_id: $sid})-[:HAS_MESSAGE]->(prev:Conversation)
                   WHERE prev.message_id <> $mid
                   WITH prev ORDER BY prev.timestamp DESC LIMIT 1
                   MATCH (m:Conversation {message_id: $mid})
                   MERGE (prev)-[:NEXT_MESSAGE]->(m)""",
                {"sid": session_id, "mid": message_id}
            )

            # Link to related graph entities (knowledge graph references)
            if related_entities:
                for entity_name in related_entities:
                    self.db.execute_write(
                        """MATCH (m:Conversation {message_id: $mid})
                           OPTIONAL MATCH (e {name: $ename})
                           WHERE e.name IS NOT NULL
                           FOREACH (_ IN CASE WHEN e IS NOT NULL THEN [1] ELSE [] END |
                               MERGE (m)-[:REFERENCES]->(e)
                           )""",
                        {"mid": message_id, "ename": entity_name}
                    )

            return message_id

        except Exception as e:
            print(f"Store message error: {e}")
            return ""

    def get_conversation_history(
        self, session_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Retrieve recent conversation turns for context.

        Args:
            session_id: Active session ID.
            limit: Max number of messages to retrieve.

        Returns:
            List of dicts with role, message, timestamp, metadata.
        """
        if not self.db.driver:
            return []

        query = """
        MATCH (s:Session {session_id: $sid})-[:HAS_MESSAGE]->(m:Conversation)
        RETURN m.role AS role, m.message AS message,
               m.timestamp AS timestamp, m.metadata AS metadata,
               m.message_id AS message_id
        ORDER BY m.timestamp ASC
        LIMIT $limit
        """
        try:
            results = self.db.execute_read(query, {"sid": session_id, "limit": limit})
            return [
                {
                    "role": r["role"],
                    "message": r["message"],
                    "timestamp": r["timestamp"],
                    "metadata": json.loads(r.get("metadata", "{}")),
                    "message_id": r["message_id"],
                }
                for r in results
            ]
        except Exception as e:
            print(f"Conversation history error: {e}")
            return []

    def get_last_message(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent message in a session."""
        history = self.get_conversation_history(session_id, limit=1)
        return history[-1] if history else None

    def search_messages(
        self, query_text: str, session_id: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search past conversation messages.

        Args:
            query_text: Text to search for.
            session_id: Optional filter to a specific session.
            limit: Max results.

        Returns:
            List of matching message dicts.
        """
        if not self.db.driver:
            return []

        if session_id:
            query = """
            MATCH (m:Conversation)
            WHERE m.session_id = $sid AND m.message CONTAINS $q
            RETURN m.role AS role, m.message AS message,
                   m.timestamp AS timestamp, m.message_id AS message_id
            ORDER BY m.timestamp DESC
            LIMIT $limit
            """
            params = {"sid": session_id, "q": query_text, "limit": limit}
        else:
            query = """
            MATCH (m:Conversation)
            WHERE m.message CONTAINS $q
            RETURN m.role AS role, m.message AS message,
                   m.timestamp AS timestamp, m.message_id AS message_id,
                   m.session_id AS session_id
            ORDER BY m.timestamp DESC
            LIMIT $limit
            """
            params = {"q": query_text, "limit": limit}

        try:
            return self.db.execute_read(query, params)
        except Exception as e:
            print(f"Message search error: {e}")
            return []

    def get_referenced_entities(self, session_id: str) -> List[Dict[str, Any]]:
        """Find all graph entities referenced in a session's messages."""
        if not self.db.driver:
            return []

        query = """
        MATCH (s:Session {session_id: $sid})-[:HAS_MESSAGE]->(:Conversation)-[:REFERENCES]->(e)
        RETURN DISTINCT e.name AS name, labels(e)[0] AS type,
                        count(*) AS mention_count
        ORDER BY mention_count DESC
        """
        try:
            return self.db.execute_read(query, {"sid": session_id})
        except Exception as e:
            print(f"Referenced entities error: {e}")
            return []

    def store_user_preference(self, session_id: str, key: str, value: Any):
        """Store a user preference for the session."""
        if not self.db.driver:
            return
        try:
            self.db.execute_write(
                """MATCH (s:Session {session_id: $sid})
                   SET s.`pref_$key` = $val""",
                {"sid": session_id, "key": key, "val": json.dumps(value) if isinstance(value, (dict, list)) else str(value)}
            )
        except Exception as e:
            print(f"Store preference error: {e}")

    def close(self):
        """Close the underlying DB connection."""
        if self.db:
            self.db.close()