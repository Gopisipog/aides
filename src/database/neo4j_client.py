from neo4j import GraphDatabase
import os

class Neo4jClient:
    """Handles connections to Neo4j and provides execution context for queries."""
    
    def __init__(self):
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "password")
        
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            # Verify connection
            self.driver.verify_connectivity()
            print("Successfully connected to Neo4j.")
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
            self.driver = None

    def close(self):
        """Close Neo4j driver connection."""
        if self.driver:
            self.driver.close()

    def execute_write(self, query, parameters=None):
        """Executes a write transaction."""
        if not self.driver:
            return None
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return result.data()

    def execute_read(self, query, parameters=None):
        """Executes a read query."""
        if not self.driver:
            return None
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return result.data()

    def insert_triplet(self, subject, subject_type, relation, obj, obj_type,
                       source_time=None, video_id=None):
        """Inserts a Subject-[Relation]->Object triplet into the graph."""
        if not self.driver:
            print("Cannot insert triplet: No Neo4j connection.")
            return

        # Sanitize labels (must be alphanumeric)
        s_label  = ''.join(e for e in subject_type if e.isalnum()) or "Entity"
        o_label  = ''.join(e for e in obj_type    if e.isalnum()) or "Entity"
        rel_type = ''.join(e for e in relation if e.isalnum() or e == '_').upper()

        query = f"""
        MERGE (s:{s_label} {{name: $subject}})
        MERGE (o:{o_label} {{name: $obj}})
        MERGE (s)-[r:{rel_type}]->(o)
        ON CREATE SET r.source_time = $source_time, r.video_id = $video_id, r.weight = 1
        ON MATCH SET  r.weight = coalesce(r.weight, 1) + 1
        """

        try:
            self.execute_write(query, {
                "subject":     subject,
                "obj":         obj,
                "source_time": source_time,
                "video_id":    video_id,
            })
            print(f"Inserted: ({subject}) -[{rel_type}]-> ({obj})")
        except Exception as e:
            print(f"Failed to insert triplet: {e}")
