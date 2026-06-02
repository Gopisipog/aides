import os
import subprocess
import sys
import time
import json
import shutil

DOCKER_COMPOSE_CONTENT = """
version: "3.8"
services:
  neo4j:
    image: neo4j:5-community
    container_name: vlkg-neo4j
    ports:
      - "7687:7687"
      - "7474:7474"
    environment:
      - NEO4J_AUTH=neo4j/password
      - NEO4J_server_memory_heap_initial__size=512m
      - NEO4J_server_memory_heap_max__size=1g
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
"""


class Neo4jManager:
    """Start/stop a local Neo4j instance via Docker Compose.

    Provides health-check polling and connection-string resolution so the
    desktop app can auto-start its database.
    """

    def __init__(self, compose_dir=None):
        self.compose_dir = compose_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "neo4j"
        )
        self.compose_file = os.path.join(self.compose_dir, "docker-compose.yml")
        self._process = None

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def uri(self):
        return os.environ.get("NEO4J_URI", "bolt://localhost:7687")

    @property
    def user(self):
        return os.environ.get("NEO4J_USER", "neo4j")

    @property
    def password(self):
        return os.environ.get("NEO4J_PASSWORD", "password")

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def ensure_running(self, timeout=60):
        """Check if Neo4j is reachable; if not, try Docker Compose up."""
        if self._ping():
            print("Neo4j is already running.")
            return True

        print("Neo4j not reachable — starting via Docker Compose …")
        self._write_compose_file()
        self._docker_compose_up()

        return self._wait_for_neo4j(timeout)

    def stop(self):
        """Tear down the Docker Compose services."""
        if not os.path.exists(self.compose_file):
            return
        print("Stopping Neo4j container …")
        subprocess.run(
            ["docker-compose", "down"],
            cwd=self.compose_dir,
            capture_output=True,
            timeout=30,
        )

    def _write_compose_file(self):
        os.makedirs(self.compose_dir, exist_ok=True)
        if not os.path.exists(self.compose_file):
            with open(self.compose_file, "w") as f:
                f.write(DOCKER_COMPOSE_CONTENT.strip() + "\n")
            print(f"Docker Compose written to {self.compose_file}")

    def _docker_compose_up(self):
        subprocess.Popen(
            ["docker-compose", "up", "-d"],
            cwd=self.compose_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _ping(self):
        """Quick connectivity check using the neo4j Python driver."""
        try:
            from neo4j import GraphDatabase
            with GraphDatabase.driver(self.uri, auth=(self.user, self.password)) as d:
                d.verify_connectivity()
                return True
        except Exception:
            return False

    def _wait_for_neo4j(self, timeout):
        start = time.time()
        while time.time() - start < timeout:
            if self._ping():
                print("Neo4j is ready.")
                return True
            time.sleep(2)
        print(f"Neo4j did not become ready within {timeout}s.")
        return False
