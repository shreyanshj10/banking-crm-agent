"""LLM-facing scoring tool (batch).

Does the DB fetching (via the Step 5 queries / session.get), then calls the
PURE app/logic/scoring.py with plain data. The scoring logic itself stays free
of any DB or LLM dependency — this tool is the only DB-aware layer.

One scoring tool serves both cases: pass many ids to build a ranked shortlist,
or a single id to explain one customer's ranking.
"""

from __future__ import annotations

from langchain_core.tools import tool

from app.db import queries
from app.db.connection import async_session_factory
from app.db.models import Customer, Product
from app.logic.scoring import score_customer as score_customer_logic


@tool
async def score_customers(customer_ids: list[str], product_id: str) -> list[dict]:
    """Score one or more customers for a product; returns them ranked by score
    (highest first). Pass many ids to build a shortlist; pass a single id to
    explain one customer's ranking.

    For each customer it fetches their attributes, holdings, and transactions,
    then runs the deterministic scorer. Each result has a score (0-100) and a
    band (high/medium/low for eligible customers, or "ineligible" if they already
    hold the product or fall below its income/credit minimum), plus human-readable
    reasons traceable to the data.

    Args:
        customer_ids: one or more customer ids (e.g. ["C00123", "C00088"]).
        product_id: the target product's id (e.g. "PL001" for Personal Loan).

    Returns a list of {customer_id, customer_name, product_id, score, band,
    reasons}, sorted by score descending (a single-element list for one id).
    """
    async with async_session_factory() as session:
        product = await session.get(Product, product_id)
        if product is None:
            return [{"error": f"product {product_id} not found"}]
        prod = {
            "product_id": product.product_id,
            "name": product.name,
            "min_income": product.min_income,
            "min_credit_score": product.min_credit_score,
        }

        results: list[dict] = []
        for customer_id in customer_ids:
            customer = await session.get(Customer, customer_id)
            if customer is None:
                results.append(
                    {"customer_id": customer_id, "error": "customer not found", "score": -1}
                )
                continue

            holdings = await queries.get_holdings(session, customer_id)
            txn_result = await queries.get_transactions(session, customer_id)
            res = score_customer_logic(
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
                product=prod,
            )
            results.append(
                {
                    "customer_id": customer.id,
                    "customer_name": customer.name,
                    "product_id": product.product_id,
                    **res,
                }
            )

    results.sort(key=lambda r: r.get("score", -1), reverse=True)
    return results
