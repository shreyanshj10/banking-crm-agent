"""LangGraph agent: explicit StateGraph (agent node + ToolNode + conditional edge).

Not create_react_agent. Async throughout — driven with `ainvoke`/`astream`; there
is no sync entry point. Conversation memory is an in-memory MemorySaver keyed by
thread_id.

`run_agent()` produces a readable, per-request tool-call trace via the standard
logging module: the incoming query, each tool call (name + full args), each tool
result (large payloads summarized), and the final response — every line tagged
with the thread_id so multi-turn conversations stay distinguishable.
"""

from __future__ import annotations

import ast
import json
import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.config import settings
from app.tools.data_tools import get_holdings, get_products, get_transactions, query_customers
from app.tools.messaging_tools import generate_message, send_whatsapp
from app.tools.recommend_tool import recommend_product
from app.tools.scoring_tool import score_customers

logger = logging.getLogger("banking_crm.agent")

TOOLS = [
    query_customers,
    get_transactions,
    get_products,
    get_holdings,
    score_customers,
    recommend_product,
    generate_message,
    send_whatsapp,
]


def build_graph():
    """Build and compile the agent graph with an in-memory checkpointer."""
    # NOTE: strict=True (Anthropic strict tool use) is omitted: langchain-anthropic
    # 0.3.1 forwards a `strict` kwarg that anthropic 0.111.0's messages.create()
    # rejects. Tool calling works without it; revisit if the SDKs are upgraded.
    llm = ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        max_tokens=2048,
    ).bind_tools(TOOLS)

    async def agent_node(state: AgentState) -> dict:
        # System prompt is prepended each turn (not stored in state, so it never
        # duplicates and the cached history stays the conversation only).
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    # handle_tool_errors=True (explicit): a failing/slow tool returns an error
    # ToolMessage to the agent instead of crashing the graph.
    tool_node = ToolNode(TOOLS, handle_tool_errors=True)

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=MemorySaver())


def _truncate(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[:limit] + "…(truncated)"


def _summarize_result(name: str, content: str) -> str:
    """Summarize a tool result for the log — full small results, counts for big ones."""
    data = None
    for parse in (json.loads, ast.literal_eval):
        try:
            data = parse(content)
            break
        except (ValueError, SyntaxError):
            continue

    if isinstance(data, list):
        return f"{len(data)} rows"
    if isinstance(data, dict):
        if isinstance(data.get("transactions"), list):
            return (
                f"{data.get('count', len(data['transactions']))} transaction(s), "
                f"credit={data.get('total_credit')}, debit={data.get('total_debit')}"
            )
        if isinstance(data.get("recommendations"), list):
            ids = [r.get("product_id") for r in data["recommendations"]]
            return f"{len(ids)} recommendation(s): {ids}"
        if "score" in data and "band" in data:
            return (
                f"score={data['score']} band={data['band']} reasons={len(data.get('reasons', []))}"
            )
        if "message" in data:
            return f"message ({len(str(data['message']))} chars)"
        if "status" in data:
            return str(data)
        return _truncate(content)
    return _truncate(content)


def _parse_content(content: str):
    for parse in (json.loads, ast.literal_eval):
        try:
            return parse(content)
        except (ValueError, SyntaxError):
            continue
    return None


async def run_agent(graph, query: str, thread_id: str) -> dict:
    """Run one RM query through the agent, logging a readable per-request trace.

    Driven via `astream` (async only). Returns a structured result:
        {"reply": str, "tool_calls": [{name, args, result}, ...],
         "generated_messages": [{customer_id, product_id, message}, ...]}
    where `result` is a short human-readable summary of each tool's output.
    so the API route can stay thin (no business logic in the route).
    """
    logger.info("[%s] QUERY: %s", thread_id, query)
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

    reply = ""
    tool_calls: list[dict] = []
    generated_messages: list[dict] = []

    async for update in graph.astream(
        {"messages": [HumanMessage(content=query)]}, config, stream_mode="updates"
    ):
        for _node, payload in update.items():
            for msg in payload.get("messages", []):
                if isinstance(msg, AIMessage):
                    for call in msg.tool_calls or []:
                        tool_calls.append(
                            {
                                "name": call["name"],
                                "args": call["args"],
                                "id": call.get("id"),
                                "result": None,
                            }
                        )
                        logger.info(
                            "[%s] TOOL CALL  %s args=%s", thread_id, call["name"], call["args"]
                        )
                    if not msg.tool_calls and (msg.content or "").strip():
                        reply = msg.content if isinstance(msg.content, str) else str(msg.content)
                        logger.info("[%s] FINAL RESPONSE: %s", thread_id, _truncate(reply, 600))
                elif isinstance(msg, ToolMessage):
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    summary = _summarize_result(msg.name, content)
                    logger.info("[%s] TOOL RESULT %s -> %s", thread_id, msg.name, summary)
                    # Attach the result to its originating call (match by id, then by name)
                    # so the UI can show "tool -> result" in the agent-path trace.
                    tc_id = getattr(msg, "tool_call_id", None)
                    target = next(
                        (
                            tc
                            for tc in tool_calls
                            if tc["id"] and tc["id"] == tc_id and tc["result"] is None
                        ),
                        None,
                    ) or next(
                        (
                            tc
                            for tc in tool_calls
                            if tc["name"] == msg.name and tc["result"] is None
                        ),
                        None,
                    )
                    if target is not None:
                        target["result"] = summary
                    if msg.name == "generate_message":
                        data = _parse_content(content)
                        if isinstance(data, dict) and data.get("message"):
                            generated_messages.append(
                                {
                                    "customer_id": data.get("customer_id"),
                                    "product_id": data.get("product_id"),
                                    "message": data.get("message"),
                                }
                            )

    # Drop the internal call id before returning — the API exposes only name/args/result.
    for tc in tool_calls:
        tc.pop("id", None)

    return {"reply": reply, "tool_calls": tool_calls, "generated_messages": generated_messages}
