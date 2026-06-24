"""SQLAlchemy ORM models — the four-table data model.

Designed to carry enough signal for the deterministic scorer and the product
recommender:
- customers: income, balance, credit score, segment, tenure, risk profile
- products:  eligibility (min_income, min_credit_score) + category
- holdings:  what each customer already holds (for cross-sell / exclusion)
- transactions: dated credit/debit activity for recency & inflow signal

All money columns use Numeric (mapped to Decimal) to avoid float rounding.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base — `Base.metadata` is the target for Alembic autogenerate."""


class Customer(Base):
    __tablename__ = "customers"

    # Identity
    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # e.g. "C00123"
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    city: Mapped[str] = mapped_column(String(80))
    age: Mapped[int] = mapped_column(Integer)
    occupation: Mapped[str] = mapped_column(String(80))

    # Scoring signal
    annual_income: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    monthly_avg_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    credit_score: Mapped[int] = mapped_column(Integer)
    segment: Mapped[str] = mapped_column(String(20))  # mass | affluent | HNI
    risk_profile: Mapped[str] = mapped_column(String(20))  # conservative | moderate | aggressive
    relationship_since: Mapped[date] = mapped_column(Date)  # tenure

    holdings: Mapped[list["Holding"]] = relationship(back_populates="customer")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(12), primary_key=True)  # e.g. "PL001"
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(20))  # loan | card | deposit | investment

    # Eligibility — read by the scorer and recommender
    min_income: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    min_credit_score: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)

    holdings: Mapped[list["Holding"]] = relationship(back_populates="product")


class Holding(Base):
    """A product a customer currently (or formerly) holds."""

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), index=True)
    opened_date: Mapped[date] = mapped_column(Date)
    balance_or_outstanding: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(10))  # active | closed

    customer: Mapped["Customer"] = relationship(back_populates="holdings")
    product: Mapped["Product"] = relationship(back_populates="holdings")


class Transaction(Base):
    """A dated credit/debit event — drives recency and inflow signal."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)  # indexed for time-window filtering
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    type: Mapped[str] = mapped_column(String(10))  # credit | debit
    category: Mapped[str] = mapped_column(String(40))  # salary | transfer | shopping | ...
    channel: Mapped[str] = mapped_column(String(20))  # upi | card | netbanking | branch

    customer: Mapped["Customer"] = relationship(back_populates="transactions")
