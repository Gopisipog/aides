"""Tool for querying the knowledge graph."""

import os
import json
from typing import Any, Dict, List, Optional

from src.database.neo4j_client import Neo4jClient
from src.agent.tools.base import BaseTool


class GraphQueryTool(BaseTool):
    """Queries the knowledge graph for entities, relationships, and statistics."""

    name = "graph_query_tool"
    description = (
        "Query the Neo4j knowledge graph. Supports: keyword search, "
        "entity lookup, relationship traversal, statistics, and custom Cypher queries."
    )

    def __init__(self):
        super().__init__()
        self.db = Neo4jClient()

    def __del__(self):
        if hasattr(self, 'db') and self.db:
            self.db.close()

    def run(
        self,
        query_type: str = "search",
        keyword: Optional[str] = None,
        entity_name: Optional[str] = None,
        relation: Optional[str] = None,
        limit: int = 20,
        custom_query: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute a graph query.

        Args:
            query_type: "search", "entity", "related", "stats", or "custom"
            keyword: Search term (for "search")
            entity_name: Node name to look up (for "entity" or "related")
            relation: Filter by relation type (for "related")
            limit: Max results
            custom_query: Raw Cypher query (for "custom")

        Returns:
            Dict with status, results, count, and message.
        """
        if not self.db.driver:
            return {"status": "error", "message": "No Neo4j connection available."}

        if query_type == "search":
            return self._search(keyword, limit)
        elif query_type == "entity":
            return self._get_entity(entity_name)
        elif query_type == "related":
            return self._get_related(entity_name, relation, limit)
        elif query_type == "stats":
            return self._get_stats()
        elif query_type == "custom":
            return self._run_custom(custom_query, kwargs.get("params", {}))
        else:
            return {"status": "error", "message": f"Unknown query_type: {query_type}. "
                    "Use 'search', 'entity', 'related', 'stats', or 'custom'."}

    def _search(self, keyword: str, limit: int) -> Dict[str, Any]:
        query = """
        MATCH (n)
        WHERE n.name CONTAINS $keyword
        RETURN n.name AS name, labels(n)[0] AS type, id(n) AS node_id
        LIMIT $limit
        """
        try:
            results = self.db.execute_read(query, {"keyword": keyword, "limit": limit})
            return {
                "status": "success",
                "results": results,
                "count": len(results),
                "message": f"Found {len(results)} node(s) matching '{keyword}'."
            }
        except Exception as e:
            return {"status": "error", "message": f"Search failed: {e}"}

    def _get_entity(self, entity_name: str) -> Dict[str, Any]:
        # Get node + properties
        query = """
        MATCH (n {name: $name})
        RETURN n.name AS name, labels(n)[0] AS type,
               properties(n) AS props, id(n) AS node_id
        """
        # Get relationships
        rel_query = """
        MATCH (n {name: $name})-[r]->(m)
        RETURN n.name AS subject, type(r) AS relation, m.name AS object,
               labels(m)[0] AS obj_type, r.weight AS weight
        LIMIT 30
        """
        rev_rel_query = """
        MATCH (m)-[r]->(n {name: $name})
        RETURN m.name AS subject, type(r) AS relation, n.name AS object,
               labels(m)[0] AS subj_type, r.weight AS weight
        LIMIT 30
        """
        try:
            node = self.db.execute_read(query, {"name": entity_name})
            outgoing = self.db.execute_read(rel_query, {"name": entity_name})
            incoming = self.db.execute_read(rev_rel_query, {"name": entity_name})

            if not node:
                return {"status": "success", "found": False,
                        "message": f"No entity named '{entity_name}' found."}

            return {
                "status": "success",
                "found": True,
                "node": node[0],
                "outgoing_relationships": outgoing,
                "incoming_relationships": incoming,
                "outgoing_count": len(outgoing),
                "incoming_count": len(incoming),
                "message": f"Found entity '{entity_name}' of type {node[0]['type']}."
            }
        except Exception as e:
            return {"status": "error", "message": f"Entity lookup failed: {e}"}

    def _get_related(self, entity_name: str, relation: Optional[str], limit: int) -> Dict[str, Any]:
        if relation:
            # Filter by specific relation type
            direction_kw = ""
            if relation.endswith("_REV"):
                rel_name = relation[:-4]
                query = f"""
                MATCH (m)-[r:{rel_name}]->(n {{name: $name}})
                RETURN m.name AS subject, type(r) AS relation, n.name AS object,
                       labels(m)[0] AS subj_type, r.weight AS weight
                LIMIT $limit
                """
            else:
                query = f"""
                MATCH (n {{name: $name}})-[r:{relation}]->(m)
                RETURN n.name AS subject, type(r) AS relation, m.name AS object,
                       labels(m)[0] AS obj_type, r.weight AS weight
                LIMIT $limit
                """
        else:
            # All relations
            query = """
            MATCH (n {name: $name})-[r]->(m)
            RETURN n.name AS subject, type(r) AS relation, m.name AS object,
                   labels(m)[0] AS obj_type, r.weight AS weight
            LIMIT $limit
            """
        try:
            results = self.db.execute_read(query, {"name": entity_name, "limit": limit})
            return {
                "status": "success",
                "results": results,
                "count": len(results),
                "message": f"Found {len(results)} relationship(s) for '{entity_name}'."
            }
        except Exception as e:
            return {"status": "error", "message": f"Relationship query failed: {e}"}

    def _get_stats(self) -> Dict[str, Any]:
        queries = {
            "node_count": "MATCH (n) RETURN count(n) AS count",
            "rel_count": "MATCH ()-[r]->() RETURN count(r) AS count",
            "types": """
                MATCH (n)
                RETURN labels(n)[0] AS type, count(*) AS count
                ORDER BY count DESC
            """,
            "relation_types": """
                MATCH ()-[r]->()
                RETURN type(r) AS relation, count(*) AS count
                ORDER BY count DESC LIMIT 20
            """,
            "degree": """
                MATCH (n)
                WITH n, COUNT { (n)--() } AS degree
                RETURN avg(degree) AS avg_degree, max(degree) AS max_degree,
                       min(degree) AS min_degree
            """
        }
        try:
            stats = {}
            for key, query in queries.items():
                result = self.db.execute_read(query)
                stats[key] = result
            return {"status": "success", "stats": stats, "message": "Graph statistics retrieved."}
        except Exception as e:
            return {"status": "error", "message": f"Stats query failed: {e}"}

    def _run_custom(self, query: str, params: dict) -> Dict[str, Any]:
        try:
            results = self.db.execute_read(query, params)
            return {
                "status": "success",
                "results": results,
                "count": len(results),
                "message": f"Custom query returned {len(results)} result(s)."
            }
        except Exception as e:
            return {"status": "error", "message": f"Custom query failed: {e}"}