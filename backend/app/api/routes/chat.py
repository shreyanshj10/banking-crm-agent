"""Chat route — thin: receive, delegate to the agent, return.

No business logic here. The agent (run_agent) does the work and assembles the
structured result; this route only maps session_id -> graph thread_id and shapes
the HTTP response.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.graph import run_agent, stream_agent

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
    result: str | None = None


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


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """Server-Sent Events variant of /chat: streams the agent's progress (tool
    calls + results) as it runs, then the final reply. /chat above is the
    non-streaming request/response endpoint.
    """
    graph = request.app.state.graph

    async def event_stream():
        try:
            async for event in stream_agent(graph, req.message, req.session_id):
                yield f"data: {json.dumps({'session_id': req.session_id, **event})}\n\n"
        except Exception as exc:  # surface the error to the client, then close cleanly
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
