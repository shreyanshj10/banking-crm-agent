"""LLM-facing product recommendation tool.

Fetches the customer and the FULL product catalog, then calls the pure
app/logic/recommendation.py. The full catalog (not a pre-filtered subset) is
passed deliberately: the "adds new exposure vs. deepens existing" logic needs
every product's category — including the ones the customer already holds — to
compute held_categories correctly.
"""

from __future__ import annotations

from langchain_core.tools import tool

from app.db import queries
from app.db.connection import async_session_factory
from app.db.models import Customer
from app.logic.recommendation import recommend_products


@tool
async def recommend_product(customer_id: str, top_n: int = 3) -> dict:
    """Recommend the best-fit products for a customer.

    Considers eligibility and what the customer already holds, ranking eligible,
    not-already-held products with a rationale for each.

    Args:
        customer_id: the customer's id (e.g. "C00123").
        top_n: how many recommendations to return (default 3).

    Returns {"customer_id", "recommendations": [{product_id, name, fit_score, rationale}, ...]}.
    """
    async with async_session_factory() as session:
        customer = await session.get(Customer, customer_id)
        if customer is None:
            return {"error": f"customer {customer_id} not found"}

        holdings = await queries.get_holdings(session, customer_id)
        catalog = await queries.get_products(session)  # FULL catalog — see module docstring

        recommendations = recommend_products(
            customer={
                "annual_income": customer.annual_income,
                "credit_score": customer.credit_score,
            },
            holdings=[{"product_id": h.product_id, "status": h.status} for h in holdings],
            products=[
                {
                    "product_id": p.product_id,
                    "name": p.name,
                    "category": p.category,
                    "min_income": p.min_income,
                    "min_credit_score": p.min_credit_score,
                }
                for p in catalog
            ],
            top_n=top_n,
        )

    return {"customer_id": customer.id, "recommendations": recommendations}
