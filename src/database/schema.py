class Neo4jSchemaManager:
    """Manages database constraints and node/edge definitions."""
    
    def __init__(self, db_client):
        self.db = db_client
        
    def setup_constraints(self):
        """Creates unique constraints for Node entities."""
        print("Setting up Neo4j constraints...")
        
        # In Neo4j 5.x, the syntax is slightly different than older versions:
        queries = [
            "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (n:Entity) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT concept_name IF NOT EXISTS FOR (n:Concept) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT competency_name IF NOT EXISTS FOR (n:Competency) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT strategy_name IF NOT EXISTS FOR (n:Strategy) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT tactic_name IF NOT EXISTS FOR (n:Tactic) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT path_name IF NOT EXISTS FOR (n:Path) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT outcome_name IF NOT EXISTS FOR (n:Outcome) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT personality_name IF NOT EXISTS FOR (n:Personality) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT context_name IF NOT EXISTS FOR (n:Context) REQUIRE n.name IS UNIQUE",
        ]
        
        for query in queries:
            try:
                self.db.execute_write(query)
            except Exception as e:
                print(f"Constraint setup note: {e}")
        print("Constraints configured.")
