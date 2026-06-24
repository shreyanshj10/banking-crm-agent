"""LLM-facing data tools — thin async wrappers over app/db/queries.py.

Each tool is a LangChain async tool (driven via `ainvoke` in the agent). Inputs
are typed (LangChain generates the JSON arg schema from the signature +
docstring); outputs are plain JSON-serializable dicts/lists (ORM rows are
converted to primitives here — this is the ORM→plain-data boundary).

All tools open their own AsyncSession from the shared factory, so they are
self-contained for the agent to call.
"""

from __future__ import annotations

from datetime import date

from langchain_core.tools import tool

from app.db import queries
from app.db.connection import async_session_factory
from app.db.models import Customer, Holding, Product, Transaction


def _customer_dict(c: Customer) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "city": c.city,
        "age": c.age,
        "occupation": c.occupation,
        "annual_income": float(c.annual_income),
        "monthly_avg_balance": float(c.monthly_avg_balance),
        "credit_score": c.credit_score,
        "segment": c.segment,
        "risk_profile": c.risk_profile,
        "relationship_since": c.relationship_since.isoformat(),
    }


def _transaction_dict(t: Transaction) -> dict:
    return {
        "id": t.id,
        "date": t.date.isoformat(),
        "amount": float(t.amount),
        "type": t.type,
        "category": t.category,
        "channel": t.channel,
    }


def _product_dict(p: Product) -> dict:
    return {
        "product_id": p.product_id,
        "name": p.name,
        "category": p.category,
        "min_income": float(p.min_income),
        "min_credit_score": p.min_credit_score,
        "description": p.description,
    }


def _holding_dict(h: Holding) -> dict:
    return {
        "product_id": h.product_id,
        "opened_date": h.opened_date.isoformat(),
        "balance_or_outstanding": float(h.balance_or_outstanding),
        "status": h.status,
    }


@tool
async def query_customers(
    min_income: float | None = None,
    max_income: float | None = None,
    min_balance: float | None = None,
    segment: str | None = None,
    city: str | None = None,
    exclude_product_id: str | None = None,
    customer_since_on_or_before: str | None = None,
    order_by: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Find customers matching optional filters (all applied in SQL).

    Args:
        min_income: keep customers with annual_income >= this.
        max_income: keep customers with annual_income <= this.
        min_balance: keep customers with monthly_avg_balance >= this.
        segment: exact segment ("mass", "affluent", "HNI").
        city: exact city.
        exclude_product_id: drop customers who actively hold this product
            (e.g. "PL001" to exclude existing personal-loan holders).
        customer_since_on_or_before: ISO date; keep customers whose relationship
            began on or before this date.
        order_by: sort the results in SQL — "balance" or "income" (highest
            first). Use this for "top N by balance/income" rather than sorting
            yourself. Defaults to credit score then income.
        limit: cap the number of rows returned (default 25; raise it if you
            explicitly need more).

    Returns a list of customer objects.
    """
    since = date.fromisoformat(customer_since_on_or_before) if customer_since_on_or_before else None
    async with async_session_factory() as session:
        rows = await queries.query_customers(
            session,
            min_income=min_income,
            max_income=max_income,
            min_balance=min_balance,
            segment=segment,
            city=city,
            exclude_product_id=exclude_product_id,
            customer_since_on_or_before=since,
            order_by=order_by,
            limit=limit,
        )
        return [_customer_dict(c) for c in rows]


@tool
async def get_transactions(
    customer_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> dict:
    """Get a customer's transactions in an optional date range, with aggregates.

    Args:
        customer_id: the customer's id (e.g. "C00123").
        start_date: ISO date lower bound (inclusive).
        end_date: ISO date upper bound (inclusive).
        limit: cap the number of transactions returned.

    Returns {"transactions": [...], "total_credit", "total_debit", "count"}.
    """
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    async with async_session_factory() as session:
        result = await queries.get_transactions(
            session, customer_id, start_date=start, end_date=end, limit=limit
        )
        return {
            "transactions": [_transaction_dict(t) for t in result["transactions"]],
            "total_credit": float(result["total_credit"]),
            "total_debit": float(result["total_debit"]),
            "count": result["count"],
        }


@tool
async def get_products(category: str | None = None) -> list[dict]:
    """List products in the catalog, optionally filtered by category.

    Args:
        category: optional exact category ("loan", "card", "deposit", "investment").

    Returns a list of product objects including eligibility thresholds.
    """
    async with async_session_factory() as session:
        rows = await queries.get_products(session, category=category)
        return [_product_dict(p) for p in rows]


@tool
async def get_holdings(customer_id: str) -> list[dict]:
    """List the products a customer currently or formerly holds.

    Args:
        customer_id: the customer's id (e.g. "C00123").

    Returns a list of holding objects.
    """
    async with async_session_factory() as session:
        rows = await queries.get_holdings(session, customer_id)
        return [_holding_dict(h) for h in rows]
