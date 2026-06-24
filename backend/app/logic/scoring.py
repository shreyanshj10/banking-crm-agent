"""Deterministic conversion scorer — PURE: no LLM, no DB, no network.

Takes plain data structures (a customer's attributes, their transactions, their
holdings, and the target product with its eligibility thresholds) and returns:

    {"score": int 0-100, "band": "high" | "medium" | "low", "reasons": [str, ...]}

The `reasons` are the explainability: every one is specific and traceable to the
input data (numbers, comparisons, dated facts), never a vague phrase. This is
what proves the output is reasoned rather than hardcoded.

Inputs are plain mappings so the function stays decoupled from the ORM:
- customer: {annual_income, credit_score, monthly_avg_balance, relationship_since: date}
- transactions: [{date: date, type: "credit"|"debit", category: str, amount: number}, ...]
- holdings: [{product_id: str, status: str}, ...]
- product: {product_id, name, min_income, min_credit_score}
"""

from __future__ import annotations

from datetime import date

HIGH_THRESHOLD = 70
MEDIUM_THRESHOLD = 40
DISQUALIFIED_SCORE = 10


def _inr(amount: float) -> str:
    """Format a rupee amount with thousands separators, e.g. ₹2,240,000."""
    return f"₹{float(amount):,.0f}"


def score_customer(
    *,
    customer: dict,
    transactions: list[dict],
    holdings: list[dict],
    product: dict,
    today: date | None = None,
) -> dict:
    today = today or date.today()

    income = float(customer["annual_income"])
    credit = int(customer["credit_score"])
    balance = float(customer["monthly_avg_balance"])

    code = product["product_id"]
    pname = product["name"]
    min_income = float(product["min_income"])
    min_credit = int(product["min_credit_score"])

    holds_product = any(
        h["product_id"] == code and h.get("status", "active") == "active" for h in holdings
    )

    # --- Disqualifiers: any one forces LOW, with the specific blocking reason ---
    disqualifiers: list[str] = []
    if holds_product:
        disqualifiers.append(f"already holds {pname} ({code})")
    if income < min_income:
        disqualifiers.append(f"income {_inr(income)} below {code} minimum {_inr(min_income)}")
    if credit < min_credit:
        disqualifiers.append(f"credit {credit} below minimum {min_credit}")

    if disqualifiers:
        return {"score": DISQUALIFIED_SCORE, "band": "low", "reasons": disqualifiers}

    # --- Eligible: accumulate points, each with a data-traceable reason ---
    score = 0
    reasons: list[str] = []

    # Income headroom above the product minimum.
    if min_income > 0:
        ratio = income / min_income
        reasons.append(f"income {_inr(income)} ≥ {code} minimum {_inr(min_income)} ({ratio:.1f}×)")
    else:
        ratio = float("inf")
        reasons.append(f"income {_inr(income)} (no income minimum for {code})")
    if ratio >= 3:
        score += 30
    elif ratio >= 2:
        score += 24
    elif ratio >= 1.5:
        score += 18
    else:  # at or just above the minimum
        score += 12

    # Credit headroom above the product minimum.
    reasons.append(f"credit {credit} ≥ {min_credit}")
    margin = credit - min_credit
    if margin >= 80:
        score += 25
    elif margin >= 40:
        score += 18
    elif margin >= 1:
        score += 12
    else:  # exactly at the minimum
        score += 10

    # Not already held (eligibility fact + small positive).
    reasons.append(f"no existing {pname} holding")
    score += 5

    # Average-balance capacity.
    if balance >= 1_000_000:
        score += 20
        reasons.append(f"high average balance {_inr(balance)}")
    elif balance >= 250_000:
        score += 14
        reasons.append(f"healthy average balance {_inr(balance)}")
    elif balance >= 50_000:
        score += 8
        reasons.append(f"moderate average balance {_inr(balance)}")
    else:
        score += 2
        reasons.append(f"low average balance {_inr(balance)}")

    # Current-month activity (engagement / repayment-capacity signal).
    month_start = today.replace(day=1)
    current = [t for t in transactions if month_start <= t["date"] <= today]
    salary_this_month = any(
        t["type"] == "credit" and t.get("category") == "salary" for t in current
    )
    if salary_this_month:
        score += 15
        reasons.append("salary credit in current month")
    elif current:
        score += 8
        reasons.append(f"{len(current)} transaction(s) in current month")
    else:
        reasons.append("no activity in current month")

    # Relationship tenure (loyalty).
    years = (today - customer["relationship_since"]).days / 365.0
    if years >= 5:
        score += 10
        reasons.append(f"{years:.0f}-year banking relationship")
    elif years >= 2:
        score += 6
        reasons.append(f"{years:.0f}-year banking relationship")
    else:
        score += 2
        reasons.append("recent banking relationship (<2 years)")

    score = max(0, min(100, score))
    if score >= HIGH_THRESHOLD:
        band = "high"
    elif score >= MEDIUM_THRESHOLD:
        band = "medium"
    else:
        band = "low"

    return {"score": score, "band": band, "reasons": reasons}
