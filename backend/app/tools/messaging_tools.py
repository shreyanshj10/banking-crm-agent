"""LLM-facing messaging tools.

- generate_message: LLM-driven, personalized. Fetches the customer and product,
  then asks Claude to write a short WhatsApp message grounded in SAFE, non-sensitive
  personalization (name, city, relationship tenure) and the actual product — never
  sensitive figures like balance, income, or credit score. Uses
  ANTHROPIC_MESSAGE_MODEL; the API key comes from settings (env). No
  temperature/top_p/top_k/budget_tokens are passed (they 400 on Opus 4.8).
- send_whatsapp: MOCKED. Sends nothing real; returns a clearly-labeled status.
"""

from __future__ import annotations

from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool

from app.config import settings
from app.db.connection import async_session_factory
from app.db.models import Customer, Product

_SYSTEM = (
    "You are a relationship manager's assistant at a retail bank. You write short, "
    "warm, professional WhatsApp messages to customers about a banking product. "
    "Keep it to 2-3 sentences. Address the customer by first name, name the product "
    "explicitly, personalize using only the relationship detail provided (e.g. how "
    "long they have banked with us, their city), and end with a soft call to action. "
    "NEVER disclose or quote sensitive personal data in the message — account "
    "balances, income, credit scores, or internal segment/score labels. Keep "
    "personalization relationship-based, not numeric. Do not invent numbers or use "
    "placeholders like [name]."
)


def _message_text(response) -> str:
    """ChatAnthropic returns content as a string or a list of content blocks."""
    content = response.content
    if isinstance(content, str):
        return content.strip()
    parts = [block.get("text", "") if isinstance(block, dict) else str(block) for block in content]
    return "".join(parts).strip()


@tool
async def generate_message(customer_id: str, product_id: str, channel: str = "whatsapp") -> dict:
    """Generate a personalized outreach message for a customer about a product.

    The message is grounded in safe, non-sensitive personalization (first name,
    city, how long they have banked with us) and the actual product — never the
    customer's balance, income, credit score, or other sensitive figures.

    Args:
        customer_id: the customer's id (e.g. "C00123").
        product_id: the product to pitch (e.g. "PL001").
        channel: delivery channel label (default "whatsapp").

    Returns {"customer_id", "product_id", "channel", "message"}.
    """
    async with async_session_factory() as session:
        customer = await session.get(Customer, customer_id)
        product = await session.get(Product, product_id)
        if customer is None:
            return {"error": f"customer {customer_id} not found"}
        if product is None:
            return {"error": f"product {product_id} not found"}

        first_name = customer.name.split()[0]
        # Only NON-sensitive personalization anchors are exposed to the message
        # model — never balance, income, credit score, or internal segment — so a
        # customer-facing message can't leak private financials.
        facts = (
            f"banking with us since {customer.relationship_since.year}; based in {customer.city}"
        )
        prompt = (
            f"Customer first name: {first_name}\n"
            f"Relationship detail to personalize with: {facts}\n"
            f"Product to offer: {product.name} — {product.description}\n"
            f"Channel: {channel}\n"
            f"Write the message now."
        )

        llm = ChatAnthropic(
            model=settings.anthropic_message_model,
            api_key=settings.anthropic_api_key,
            max_tokens=300,
        )
        response = await llm.ainvoke([("system", _SYSTEM), ("human", prompt)])

    return {
        "customer_id": customer.id,
        "product_id": product.product_id,
        "channel": channel,
        "message": _message_text(response),
    }


@tool
async def send_whatsapp(customer_id: str, message: str) -> dict:
    """Send a WhatsApp message to a customer. MOCKED — nothing is actually sent.

    This is a stub for the assignment: it does not call any messaging gateway.

    Args:
        customer_id: the customer's id (e.g. "C00123").
        message: the message body to "send".

    Returns a clearly-labeled mock status object.
    """
    async with async_session_factory() as session:
        customer = await session.get(Customer, customer_id)
        to_phone = customer.phone if customer else None

    return {
        "status": "mock_sent",
        "to_phone": to_phone,
        "customer_id": customer_id,
        "timestamp": datetime.now().isoformat(),
        "note": "MOCK — no real WhatsApp message was sent",
    }
