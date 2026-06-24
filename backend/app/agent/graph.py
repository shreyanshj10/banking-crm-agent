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
from app.tools.scoring_tool import score_customer

logger = logging.getLogger("banking_crm.agent")

TOOLS = [
    query_customers,
    get_transactions,
    get_products,
    get_holdings,
    score_customer,
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


async def run_agent(graph, query: str, thread_id: str) -> AIMessage | None:
    """Run one RM query through the agent, logging a readable per-request trace.

    Driven via `astream` (async only). Returns the final AIMessage.
    """
    logger.info("[%s] QUERY: %s", thread_id, query)
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    final: AIMessage | None = None

    async for update in graph.astream(
        {"messages": [HumanMessage(content=query)]}, config, stream_mode="updates"
    ):
        for _node, payload in update.items():
            for msg in payload.get("messages", []):
                if isinstance(msg, AIMessage):
                    for call in msg.tool_calls or []:
                        logger.info(
                            "[%s] TOOL CALL  %s args=%s", thread_id, call["name"], call["args"]
                        )
                    if not msg.tool_calls and (msg.content or "").strip():
                        final = msg
                        logger.info(
                            "[%s] FINAL RESPONSE: %s",
                            thread_id,
                            _truncate(
                                msg.content if isinstance(msg.content, str) else str(msg.content),
                                600,
                            ),
                        )
                elif isinstance(msg, ToolMessage):
                    logger.info(
                        "[%s] TOOL RESULT %s -> %s",
                        thread_id,
                        msg.name,
                        _summarize_result(
                            msg.name,
                            msg.content if isinstance(msg.content, str) else str(msg.content),
                        ),
                    )

    return final
