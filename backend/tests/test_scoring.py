"""Tests for the deterministic scorer — written before the implementation (TDD).

These pin the contract: a clearly-strong customer scores HIGH with specific,
data-traceable reasons; a clearly-weak/ineligible customer scores LOW; the
eligibility threshold is inclusive (>=); and the function is pure/idempotent.
"""

from datetime import date

from app.logic.scoring import score_customer

TODAY = date(2026, 6, 24)
MONTH = date(2026, 6, 1)  # current month for TODAY

PERSONAL_LOAN = {
    "product_id": "PL001",
    "name": "Personal Loan",
    "min_income": 600_000,
    "min_credit_score": 700,
}


def _salary(day: date, amount: float = 150_000) -> dict:
    return {"date": day, "type": "credit", "category": "salary", "amount": amount}


def _strong_customer_inputs() -> dict:
    return dict(
        customer={
            "annual_income": 2_240_000,
            "credit_score": 802,
            "monthly_avg_balance": 1_200_000,
            "relationship_since": date(2019, 3, 1),  # ~7 years
        },
        transactions=[
            _salary(date(2026, 6, 5)),  # current month
            _salary(date(2026, 5, 5)),
            {"date": date(2026, 6, 10), "type": "debit", "category": "shopping", "amount": 8000},
        ],
        holdings=[{"product_id": "SA001", "status": "active"}],  # no personal loan
        product=PERSONAL_LOAN,
        today=TODAY,
    )


def test_strong_customer_scores_high_with_specific_reasons():
    result = score_customer(**_strong_customer_inputs())

    assert result["band"] == "high"
    assert result["score"] >= 70
    reasons = result["reasons"]

    # Reasons must be specific and traceable to the data, not vague.
    assert any("≥ PL001 minimum" in r for r in reasons), reasons  # income eligibility w/ numbers
    assert "credit 802 ≥ 700" in reasons, reasons  # exact credit comparison
    assert any(r.startswith("no existing Personal Loan") for r in reasons), reasons
    assert "salary credit in current month" in reasons, reasons
    # Guard against vagueness.
    assert not any("good profile" in r.lower() for r in reasons), reasons


def test_ineligible_low_income_scores_low():
    inputs = _strong_customer_inputs()
    inputs["customer"] = {**inputs["customer"], "annual_income": 300_000}  # below PL min 600k

    result = score_customer(**inputs)

    assert result["band"] == "low"
    assert any("below PL001 minimum" in r for r in result["reasons"]), result["reasons"]


def test_already_holds_product_scores_low_even_with_strong_profile():
    # High income + great credit, but already holds the personal loan -> LOW.
    # This guards against a scorer that just rates every wealthy customer high.
    inputs = _strong_customer_inputs()
    inputs["holdings"] = [
        {"product_id": "SA001", "status": "active"},
        {"product_id": "PL001", "status": "active"},
    ]

    result = score_customer(**inputs)

    assert result["band"] == "low"
    assert any("already holds" in r.lower() for r in result["reasons"]), result["reasons"]


def test_eligibility_threshold_is_inclusive():
    # Income and credit EXACTLY at the product minimums must be ELIGIBLE (>=),
    # so the customer is not forced low purely by the eligibility gate.
    inputs = _strong_customer_inputs()
    inputs["customer"] = {
        **inputs["customer"],
        "annual_income": 600_000,  # == min_income
        "credit_score": 700,  # == min_credit_score
        "monthly_avg_balance": 800_000,
    }

    result = score_customer(**inputs)

    assert result["band"] != "low", result
    assert any("≥ PL001 minimum" in r for r in result["reasons"]), result["reasons"]
    assert "credit 700 ≥ 700" in result["reasons"], result["reasons"]


def test_weak_scores_below_strong():
    strong = score_customer(**_strong_customer_inputs())
    weak_inputs = _strong_customer_inputs()
    weak_inputs["customer"] = {**weak_inputs["customer"], "annual_income": 300_000}
    weak = score_customer(**weak_inputs)
    assert weak["score"] < strong["score"]


def test_idempotent_same_input_same_output():
    a = score_customer(**_strong_customer_inputs())
    b = score_customer(**_strong_customer_inputs())
    assert a == b
