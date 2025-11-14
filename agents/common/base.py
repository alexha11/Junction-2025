from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from pydantic import BaseModel


class ToolSchema(BaseModel):
    """Schema each MCP tool payload should inherit from."""


class BaseMCPAgent(ABC):
    """Tiny harness that mimics a MCP-compatible agent service.

    The OpenAI Agents SDK exposes MCP tool servers; once that integration is
    available here we only need to replace the ``serve`` function to hook into
    ``openai.resources.mcp`` primitives. For now we keep things synchronous and
    lightweight so the rest of the stack can rely on deterministic behavior.
    """

    name: str

    def __init__(self, name: str) -> None:
        self.name = name
        self._tools: dict[str, Callable[[Any], Any]] = {}

    def register_tool(self, name: str, handler: Callable[[Any], Any]) -> None:
        self._tools[name] = handler

    def call_tool(self, name: str, payload: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool {name} not registered for agent {self.name}")
        return self._tools[name](payload)

    @abstractmethod
    def configure(self) -> None:
        """Derived classes register their MCP tools here."""

    def serve(self) -> None:
        self.configure()
        print(f"{self.name} registered tools: {list(self._tools)}")
