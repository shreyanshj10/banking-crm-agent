"""Tests for the deterministic scorer — NEW contract (refinements A + B).

A: disqualified customers (already hold the product, or below the income/credit
   minimum) get band "ineligible" — a status distinct from "low". low/medium/high
   are reserved for ELIGIBLE customers, graded by strength.
B: eligible point weights are compressed so scores spread — a clearly-strong HNI
   prospect scores high, a barely/modestly-eligible customer lands medium (not
   high), and a weak-but-eligible customer lands low.
"""

from datetime import date

from app.logic.scoring import score_customer

TODAY = date(2026, 6, 24)

PERSONAL_LOAN = {
    "product_id": "PL001",
    "name": "Personal Loan",
    "min_income": 600_000,
    "min_credit_score": 700,
}


def _salary(day: date, amount: float = 150_000) -> dict:
    return {"date": day, "type": "credit", "category": "salary", "amount": amount}


def _strong_customer_inputs() -> dict:
    """Clearly-strong HNI prospect."""
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
    assert any("≥ PL001 minimum" in r for r in reasons), reasons
    assert "credit 802 ≥ 700" in reasons, reasons
    assert any(r.startswith("no existing Personal Loan") for r in reasons), reasons
    assert "salary credit in current month" in reasons, reasons
    assert not any("good profile" in r.lower() for r in reasons), reasons


def test_modestly_eligible_customer_lands_medium_not_high():
    # Just over the line on income/credit, decent but unremarkable: should be
    # MEDIUM — not high (the old saturating behavior) and not ineligible.
    inputs = _strong_customer_inputs()
    inputs["customer"] = {
        "annual_income": 780_000,  # 1.3x the minimum
        "credit_score": 745,  # +45 over minimum
        "monthly_avg_balance": 350_000,
        "relationship_since": date(2022, 6, 1),  # ~4 years
    }

    result = score_customer(**inputs)

    assert result["band"] == "medium", result
    assert result["band"] != "high"


def test_weak_but_eligible_customer_lands_low():
    # Eligible (meets both minimums) but otherwise weak: low balance, no
    # current-month activity, short tenure -> LOW (reserved for weak eligible).
    inputs = _strong_customer_inputs()
    inputs["customer"] = {
        "annual_income": 600_000,  # exactly the minimum
        "credit_score": 700,  # exactly the minimum
        "monthly_avg_balance": 40_000,
        "relationship_since": date(2026, 1, 1),  # <1 year
    }
    inputs["transactions"] = [_salary(date(2026, 5, 5))]  # last month only — none current

    result = score_customer(**inputs)

    assert result["band"] == "low", result


def test_ineligible_low_income_is_ineligible_not_low():
    inputs = _strong_customer_inputs()
    inputs["customer"] = {**inputs["customer"], "annual_income": 300_000}  # below PL min

    result = score_customer(**inputs)

    assert result["band"] == "ineligible", result
    assert any("below PL001 minimum" in r for r in result["reasons"]), result["reasons"]


def test_already_holds_product_is_ineligible():
    # High income + great credit, but already holds the personal loan -> INELIGIBLE.
    inputs = _strong_customer_inputs()
    inputs["holdings"] = [
        {"product_id": "SA001", "status": "active"},
        {"product_id": "PL001", "status": "active"},
    ]

    result = score_customer(**inputs)

    assert result["band"] == "ineligible", result
    assert any("already holds" in r.lower() for r in result["reasons"]), result["reasons"]


def test_eligibility_threshold_is_inclusive():
    # Income and credit EXACTLY at the minimums must be ELIGIBLE (>=), so the
    # customer is graded (not ineligible).
    inputs = _strong_customer_inputs()
    inputs["customer"] = {
        **inputs["customer"],
        "annual_income": 600_000,  # == min_income
        "credit_score": 700,  # == min_credit_score
        "monthly_avg_balance": 800_000,
    }

    result = score_customer(**inputs)

    assert result["band"] in ("low", "medium", "high"), result
    assert result["band"] != "ineligible", result
    assert any("≥ PL001 minimum" in r for r in result["reasons"]), result["reasons"]
    assert "credit 700 ≥ 700" in result["reasons"], result["reasons"]


def test_ineligible_scores_below_strong():
    strong = score_customer(**_strong_customer_inputs())
    inputs = _strong_customer_inputs()
    inputs["customer"] = {**inputs["customer"], "annual_income": 300_000}
    ineligible = score_customer(**inputs)
    assert ineligible["score"] < strong["score"]


def test_idempotent_same_input_same_output():
    a = score_customer(**_strong_customer_inputs())
    b = score_customer(**_strong_customer_inputs())
    assert a == b
