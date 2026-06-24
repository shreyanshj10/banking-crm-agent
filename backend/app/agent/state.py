"""Agent graph state.

The conversation history IS the working context: tool results accumulate as
ToolMessages, so the LLM reasons over what it has fetched. `add_messages` is the
reducer that appends new messages each turn.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
