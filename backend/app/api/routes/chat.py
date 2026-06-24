"""Chat route — thin: receive, delegate to the agent, return.

No business logic here. The agent (run_agent) does the work and assembles the
structured result; this route only maps session_id -> graph thread_id and shapes
the HTTP response.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.agent.graph import run_agent

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str


class GeneratedMessage(BaseModel):
    customer_id: str | None = None
    product_id: str | None = None
    message: str


class ToolCall(BaseModel):
    name: str
    args: dict


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tool_calls: list[ToolCall]
    generated_messages: list[GeneratedMessage]


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    # The compiled graph is built once at startup and shared, so its in-memory
    # MemorySaver carries conversation state across requests.
    graph = request.app.state.graph
    # session_id maps directly to the agent's conversation thread_id.
    result = await run_agent(graph, req.message, req.session_id)
    return ChatResponse(session_id=req.session_id, **result)
