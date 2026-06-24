"""Parameterized, async data-access queries backing the LLM data tools.

Every query is built with SQLAlchemy ORM expressions, so all user-supplied
values become **bound parameters** — there is no string concatenation or
f-string interpolation of values into SQL anywhere in this module.

All functions are async and run on an AsyncSession.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Customer, Holding, Product, Transaction

# Whitelist of sortable columns: maps a safe key to an ORM column. The agent
# supplies only a key from this map, so a raw column name from input is never
# interpolated into SQL.
_SORTABLE_COLUMNS = {
    "balance": Customer.monthly_avg_balance,
    "income": Customer.annual_income,
    "credit_score": Customer.credit_score,
}


def month_window(today: date | None = None) -> tuple[date, date]:
    """Return (first day of the current month, today), computed relative to now.

    The window is derived from the current date — never a hardcoded month — so
    "this month" filtering stays correct whenever it runs (matching how the seed
    anchors its dates).
    """
    today = today or date.today()
    return today.replace(day=1), today


async def query_customers(
    session: AsyncSession,
    *,
    min_income: float | None = None,
    max_income: float | None = None,
    min_balance: float | None = None,
    segment: str | None = None,
    city: str | None = None,
    exclude_product_id: str | None = None,
    customer_since_on_or_before: date | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[Customer]:
    """Filter customers in SQL. All predicates use bound parameters.

    `exclude_product_id` drops customers who hold that product actively
    (e.g. exclude existing personal-loan holders) via a correlated NOT EXISTS.
    `customer_since_on_or_before` keeps customers whose relationship began on or
    before the given date (a tenure filter).
    `order_by` sorts in SQL by a whitelisted column ("balance" or "income",
    highest first); any other/empty value falls back to the default ordering.
    """
    stmt = select(Customer)

    if min_income is not None:
        stmt = stmt.where(Customer.annual_income >= min_income)
    if max_income is not None:
        stmt = stmt.where(Customer.annual_income <= max_income)
    if min_balance is not None:
        stmt = stmt.where(Customer.monthly_avg_balance >= min_balance)
    if segment is not None:
        stmt = stmt.where(Customer.segment == segment)
    if city is not None:
        stmt = stmt.where(Customer.city == city)
    if customer_since_on_or_before is not None:
        stmt = stmt.where(Customer.relationship_since <= customer_since_on_or_before)
    if exclude_product_id is not None:
        active_holding = (
            select(Holding.id)
            .where(Holding.customer_id == Customer.id)
            .where(Holding.product_id == exclude_product_id)
            .where(Holding.status == "active")
        )
        stmt = stmt.where(~active_holding.exists())

    sort_column = _SORTABLE_COLUMNS.get(order_by) if order_by else None
    if sort_column is not None:
        stmt = stmt.order_by(sort_column.desc())  # highest first
    else:
        # default ordering (also the safe fallback for an unrecognized order_by)
        stmt = stmt.order_by(Customer.credit_score.desc(), Customer.annual_income.desc())
    if limit is not None:
        stmt = stmt.limit(limit)

    return list(await session.scalars(stmt))


async def get_transactions(
    session: AsyncSession,
    customer_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int | None = None,
) -> dict:
    """Transactions for a customer within an optional date range, in SQL.

    Returns the (SQL-filtered) transactions plus lightweight aggregates:
        {"transactions": [...], "total_credit", "total_debit", "count"}
    Aggregates are derived from the already-filtered set.
    """
    stmt = select(Transaction).where(Transaction.customer_id == customer_id)
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)
    stmt = stmt.order_by(Transaction.date.desc())
    if limit is not None:
        stmt = stmt.limit(limit)

    txns = list(await session.scalars(stmt))
    total_credit = sum((t.amount for t in txns if t.type == "credit"), Decimal("0"))
    total_debit = sum((t.amount for t in txns if t.type == "debit"), Decimal("0"))
    return {
        "transactions": txns,
        "total_credit": total_credit,
        "total_debit": total_debit,
        "count": len(txns),
    }


async def get_products(
    session: AsyncSession,
    *,
    category: str | None = None,
) -> list[Product]:
    """Product catalog, optionally filtered by category (bound parameter)."""
    stmt = select(Product)
    if category is not None:
        stmt = stmt.where(Product.category == category)
    stmt = stmt.order_by(Product.product_id)
    return list(await session.scalars(stmt))


async def get_holdings(
    session: AsyncSession,
    customer_id: str,
) -> list[Holding]:
    """All holdings for a given customer (bound parameter)."""
    stmt = select(Holding).where(Holding.customer_id == customer_id).order_by(Holding.product_id)
    return list(await session.scalars(stmt))
