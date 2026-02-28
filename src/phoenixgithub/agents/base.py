"""Base agent — shared LLM invocation logic for all specialized agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all specialized agents."""

    role: str = ""
    system_prompt: str = ""

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def invoke(self, user_prompt: str) -> str:
        """Send a prompt to the LLM with this agent's system prompt."""
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self.llm.invoke(messages)
        return response.content

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute this agent's task. Returns outputs to merge into run context."""
        ...
