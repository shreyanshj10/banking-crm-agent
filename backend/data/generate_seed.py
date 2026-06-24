"""Synthetic data generator for the banking CRM.

Run AFTER migrations (the tables must already exist):

    ./.venv/bin/python data/generate_seed.py

Idempotent by reset: the generator first deletes all rows from the four tables
(children before parents), then inserts a fresh dataset. Re-running therefore
re-seeds rather than double-seeding.

Two guarantees the seed makes:
1. Dates are anchored to `date.today()` at run time — transactions and holdings
   are spread over recent months relative to *now*, and every customer has at
   least one transaction inside the current calendar month. So "this month"
   filtering returns rows whenever the evaluator runs it.
2. A handful of customers are clearly strong personal-loan prospects (high
   income, strong credit, NO personal-loan holding, current-month activity), so
   the canonical RM query returns a real shortlist.
"""

from __future__ import annotations

import asyncio
import pathlib
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

# Make the `app` package importable when this file is run directly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import delete  # noqa: E402

from app.db.connection import async_session_factory, engine  # noqa: E402
from app.db.models import Customer, Holding, Product, Transaction  # noqa: E402

# Deterministic structure (amounts, picks); dates still anchor to today.
RNG = random.Random(42)

TODAY = date.today()
MONTH_START = TODAY.replace(day=1)

PERSONAL_LOAN_ID = "PL001"

FIRST_NAMES = [
    "Priya",
    "Arjun",
    "Ananya",
    "Rohan",
    "Kavya",
    "Vikram",
    "Neha",
    "Aditya",
    "Sneha",
    "Karan",
    "Divya",
    "Rahul",
    "Pooja",
    "Amit",
    "Ishaan",
    "Meera",
    "Sanjay",
    "Riya",
    "Nikhil",
    "Tanvi",
]
LAST_NAMES = [
    "Sharma",
    "Iyer",
    "Reddy",
    "Mehta",
    "Nair",
    "Gupta",
    "Patel",
    "Verma",
    "Rao",
    "Khanna",
    "Bose",
    "Desai",
    "Kapoor",
    "Menon",
    "Joshi",
]
CITIES = ["Mumbai", "Bengaluru", "Delhi", "Pune", "Hyderabad", "Chennai", "Kolkata"]
OCCUPATIONS = [
    "Software Engineer",
    "Doctor",
    "Teacher",
    "Business Owner",
    "Consultant",
    "Architect",
    "Accountant",
    "Sales Manager",
    "Civil Servant",
    "Designer",
]
RISK_PROFILES = ["conservative", "moderate", "aggressive"]

DEBIT_CATEGORIES = ["shopping", "dining", "utilities", "transfer", "travel", "groceries"]
CHANNELS = ["upi", "card", "netbanking", "branch"]


def money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def products() -> list[Product]:
    """Product catalog with eligibility thresholds the scorer/recommender read."""
    return [
        Product(
            product_id="SA001",
            name="Savings Account",
            category="deposit",
            min_income=money(0),
            min_credit_score=0,
            description="Everyday savings account with zero eligibility bar.",
        ),
        Product(
            product_id="FD001",
            name="Fixed Deposit",
            category="deposit",
            min_income=money(0),
            min_credit_score=0,
            description="Term deposit with assured returns.",
        ),
        Product(
            product_id="MF001",
            name="Mutual Fund SIP",
            category="investment",
            min_income=money(400000),
            min_credit_score=0,
            description="Systematic investment plan across equity/debt funds.",
        ),
        Product(
            product_id="CC002",
            name="Everyday Credit Card",
            category="card",
            min_income=money(300000),
            min_credit_score=680,
            description="Entry-level rewards credit card.",
        ),
        Product(
            product_id="CC001",
            name="Platinum Credit Card",
            category="card",
            min_income=money(800000),
            min_credit_score=740,
            description="Premium credit card with travel and lounge benefits.",
        ),
        Product(
            product_id=PERSONAL_LOAN_ID,
            name="Personal Loan",
            category="loan",
            min_income=money(600000),
            min_credit_score=700,
            description="Unsecured personal loan for salaried and self-employed.",
        ),
        Product(
            product_id="HL001",
            name="Home Loan",
            category="loan",
            min_income=money(1000000),
            min_credit_score=720,
            description="Long-tenure secured home loan.",
        ),
    ]


def segment_profile(segment: str) -> tuple[float, float, int]:
    """Return (annual_income, monthly_avg_balance, credit_score) for a segment."""
    if segment == "HNI":
        income = RNG.uniform(2_500_000, 12_000_000)
        balance = RNG.uniform(1_500_000, 20_000_000)
        credit = RNG.randint(740, 820)
    elif segment == "affluent":
        income = RNG.uniform(700_000, 2_500_000)
        balance = RNG.uniform(150_000, 1_500_000)
        credit = RNG.randint(700, 800)
    else:  # mass
        income = RNG.uniform(200_000, 700_000)
        balance = RNG.uniform(5_000, 150_000)
        credit = RNG.randint(600, 740)
    return income, balance, credit


def make_customer(idx: int, segment: str, *, forced: dict | None = None) -> Customer:
    income, balance, credit = segment_profile(segment)
    attrs = dict(
        id=f"C{idx:05d}",
        name=f"{RNG.choice(FIRST_NAMES)} {RNG.choice(LAST_NAMES)}",
        phone=f"+9198{RNG.randint(10_000_000, 99_999_999)}",
        city=RNG.choice(CITIES),
        age=RNG.randint(24, 65),
        occupation=RNG.choice(OCCUPATIONS),
        annual_income=money(income),
        monthly_avg_balance=money(balance),
        credit_score=credit,
        segment=segment,
        risk_profile=RNG.choice(RISK_PROFILES),
        relationship_since=TODAY - timedelta(days=RNG.randint(180, 12 * 365)),
    )
    if forced:
        attrs.update(forced)
    return Customer(**attrs)


def date_in_month(months_ago: int) -> date:
    """A date inside the calendar month `months_ago` months before this one.

    months_ago=0 -> current month, between the 1st and today.
    """
    y = MONTH_START.year
    m = MONTH_START.month - months_ago
    while m <= 0:
        m += 12
        y -= 1
    first = date(y, m, 1)
    if months_ago == 0:
        last_day = TODAY.day
    else:
        # last day of that month
        nxt = date(y + (m // 12), (m % 12) + 1, 1)
        last_day = (nxt - timedelta(days=1)).day
    return first.replace(day=RNG.randint(1, max(1, last_day)))


def transactions_for(customer: Customer) -> list[Transaction]:
    """Salary credits for the last 6 months (incl. current) + assorted debits.

    Every customer gets a current-month salary credit, so the current-month
    slice is always non-empty.
    """
    txns: list[Transaction] = []
    monthly_salary = float(customer.annual_income) / 12.0

    # Salary credit each of the last 6 months, including the current one.
    for months_ago in range(6):
        txns.append(
            Transaction(
                customer_id=customer.id,
                date=date_in_month(months_ago),
                amount=money(monthly_salary * RNG.uniform(0.85, 1.0)),
                type="credit",
                category="salary",
                channel="netbanking",
            )
        )

    # Assorted debits over the last ~180 days (some land in the current month).
    for _ in range(RNG.randint(12, 28)):
        txns.append(
            Transaction(
                customer_id=customer.id,
                date=TODAY - timedelta(days=RNG.randint(0, 180)),
                amount=money(RNG.uniform(200, max(2000, monthly_salary * 0.4))),
                type="debit",
                category=RNG.choice(DEBIT_CATEGORIES),
                channel=RNG.choice(CHANNELS),
            )
        )
    return txns


def holdings_for(customer: Customer, *, allow_personal_loan: bool) -> list[Holding]:
    """Everyone holds a savings account; others assigned loosely by eligibility."""
    held: list[Holding] = [
        Holding(
            customer_id=customer.id,
            product_id="SA001",
            opened_date=customer.relationship_since,
            balance_or_outstanding=customer.monthly_avg_balance,
            status="active",
        )
    ]

    def maybe_add(product_id: str, prob: float, outstanding: float) -> None:
        if RNG.random() < prob:
            held.append(
                Holding(
                    customer_id=customer.id,
                    product_id=product_id,
                    opened_date=TODAY - timedelta(days=RNG.randint(60, 1500)),
                    balance_or_outstanding=money(outstanding),
                    status="active",
                )
            )

    income = float(customer.annual_income)
    if income >= 400_000:
        maybe_add("MF001", 0.4, RNG.uniform(20_000, 500_000))
    if income >= 300_000 and customer.credit_score >= 680:
        maybe_add("CC002", 0.5, RNG.uniform(0, 80_000))
    if income >= 800_000 and customer.credit_score >= 740:
        maybe_add("CC001", 0.4, RNG.uniform(0, 200_000))
    if allow_personal_loan and income >= 600_000 and customer.credit_score >= 700:
        maybe_add(PERSONAL_LOAN_ID, 0.45, RNG.uniform(50_000, 800_000))
    return held


async def reset(session) -> None:
    """Idempotency: clear all rows (children first) so re-runs don't double-seed."""
    await session.execute(delete(Transaction))
    await session.execute(delete(Holding))
    await session.execute(delete(Customer))
    await session.execute(delete(Product))
    await session.commit()


def build_dataset() -> tuple[list, list, list]:
    customers: list[Customer] = []
    holdings: list[Holding] = []
    transactions: list[Transaction] = []

    # 55 random customers across segments.
    segments = (["mass"] * 30) + (["affluent"] * 18) + (["HNI"] * 7)
    RNG.shuffle(segments)
    for i, seg in enumerate(segments, start=1):
        c = make_customer(i, seg)
        customers.append(c)
        holdings.extend(holdings_for(c, allow_personal_loan=True))
        transactions.extend(transactions_for(c))

    # 5 GUARANTEED strong personal-loan prospects:
    #   high income, strong credit, NO personal-loan holding, current-month activity.
    start = len(segments) + 1
    for j in range(5):
        c = make_customer(
            start + j,
            "affluent",
            forced=dict(
                annual_income=money(RNG.uniform(1_500_000, 3_000_000)),
                credit_score=RNG.randint(760, 810),
                monthly_avg_balance=money(RNG.uniform(400_000, 1_500_000)),
            ),
        )
        customers.append(c)
        # allow_personal_loan=False guarantees no PL001 holding for these.
        holdings.extend(holdings_for(c, allow_personal_loan=False))
        transactions.extend(transactions_for(c))  # includes a current-month salary credit

    return customers, holdings, transactions


async def seed() -> None:
    async with async_session_factory() as session:
        await reset(session)

        session.add_all(products())
        await session.commit()

        customers, holdings, transactions = build_dataset()
        session.add_all(customers)
        await session.commit()
        session.add_all(holdings)
        session.add_all(transactions)
        await session.commit()

        print(
            f"Seeded: {len(customers)} customers, {len(products())} products, "
            f"{len(holdings)} holdings, {len(transactions)} transactions "
            f"(anchored to {TODAY.isoformat()})."
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
