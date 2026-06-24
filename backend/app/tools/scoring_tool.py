"""LLM-facing scoring tool.

Does the DB fetching (via the Step 5 queries / session.get), then calls the
PURE app/logic/scoring.py with plain data. The scoring logic itself stays free
of any DB or LLM dependency — this tool is the only DB-aware layer.
"""

from __future__ import annotations

from langchain_core.tools import tool

from app.db import queries
from app.db.connection import async_session_factory
from app.db.models import Customer, Product
from app.logic.scoring import score_customer as score_customer_logic


@tool
async def score_customer(customer_id: str, product_id: str) -> dict:
    """Score how likely a customer is to convert for a given product.

    Fetches the customer's attributes, holdings, and transactions, then runs the
    deterministic scorer. Returns a score (0-100), a band (high/medium/low for
    eligible customers, or "ineligible" if they already hold the product or fall
    below its income/credit minimum), and human-readable reasons traceable to the data.

    Args:
        customer_id: the customer's id (e.g. "C00123").
        product_id: the target product's id (e.g. "PL001" for Personal Loan).

    Returns {"customer_id", "customer_name", "product_id", "score", "band", "reasons"}.
    """
    async with async_session_factory() as session:
        customer = await session.get(Customer, customer_id)
        product = await session.get(Product, product_id)
        if customer is None:
            return {"error": f"customer {customer_id} not found"}
        if product is None:
            return {"error": f"product {product_id} not found"}

        holdings = await queries.get_holdings(session, customer_id)
        txn_result = await queries.get_transactions(session, customer_id)

        result = score_customer_logic(
            customer={
                "annual_income": customer.annual_income,
                "credit_score": customer.credit_score,
                "monthly_avg_balance": customer.monthly_avg_balance,
                "relationship_since": customer.relationship_since,
            },
            transactions=[
                {"date": t.date, "type": t.type, "category": t.category, "amount": t.amount}
                for t in txn_result["transactions"]
            ],
            holdings=[{"product_id": h.product_id, "status": h.status} for h in holdings],
            product={
                "product_id": product.product_id,
                "name": product.name,
                "min_income": product.min_income,
                "min_credit_score": product.min_credit_score,
            },
        )

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "product_id": product.product_id,
        **result,
    }
