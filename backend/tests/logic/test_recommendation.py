"""Tests for the pure product-fit recommender — written before implementation."""

from app.logic.recommendation import recommend_products

CATALOG = [
    {
        "product_id": "SA001",
        "name": "Savings Account",
        "category": "deposit",
        "min_income": 0,
        "min_credit_score": 0,
    },
    {
        "product_id": "FD001",
        "name": "Fixed Deposit",
        "category": "deposit",
        "min_income": 0,
        "min_credit_score": 0,
    },
    {
        "product_id": "MF001",
        "name": "Mutual Fund SIP",
        "category": "investment",
        "min_income": 400_000,
        "min_credit_score": 0,
    },
    {
        "product_id": "CC001",
        "name": "Platinum Credit Card",
        "category": "card",
        "min_income": 800_000,
        "min_credit_score": 740,
    },
    {
        "product_id": "PL001",
        "name": "Personal Loan",
        "category": "loan",
        "min_income": 600_000,
        "min_credit_score": 700,
    },
    {
        "product_id": "HL001",
        "name": "Home Loan",
        "category": "loan",
        "min_income": 1_000_000,
        "min_credit_score": 720,
    },
]


def _inputs() -> dict:
    return dict(
        customer={"annual_income": 900_000, "credit_score": 780},
        holdings=[{"product_id": "SA001", "status": "active"}],  # holds savings only
        products=CATALOG,
    )


def test_excludes_held_and_ineligible_products():
    recs = recommend_products(**_inputs())
    ids = [r["product_id"] for r in recs]

    assert "SA001" not in ids, "held product must not be recommended"
    assert "HL001" not in ids, "income 900k < HL min 1,000,000 -> ineligible"


def test_recommends_eligible_unheld_products_with_rationale():
    recs = recommend_products(**_inputs(), top_n=3)
    ids = [r["product_id"] for r in recs]

    assert len(recs) <= 3
    assert "PL001" in ids and "CC001" in ids
    for r in recs:
        assert {"product_id", "name", "fit_score", "rationale"} <= set(r)
        assert "eligible" in r["rationale"].lower()


def test_sorted_by_fit_descending():
    recs = recommend_products(**_inputs(), top_n=10)
    scores = [r["fit_score"] for r in recs]
    assert scores == sorted(scores, reverse=True)


def test_idempotent():
    assert recommend_products(**_inputs()) == recommend_products(**_inputs())
