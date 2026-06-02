"""Base class for all agent tools."""

from typing import Any, Dict, Optional

class BaseTool:
    """Abstract base class for agent tools.

    Each tool wraps a piece of functionality (ingestion, query, enrichment, etc.)
    and exposes a uniform interface for the agent orchestrator.
    """

    name: str = "base"
    description: str = "Base tool — override in subclass."

    def __init__(self):
        self._name = self.__class__.__name__

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with the given parameters.

        Subclasses must override this method.
        Returns a dict with at least:
            - status: "success" | "error"
            - result: the main output
            - message: human-readable description
        """
        raise NotImplementedError("Subclasses must implement run()")

    @property
    def tool_name(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return f"<Tool: {self._name}>"