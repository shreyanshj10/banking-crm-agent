"""Pure product-fit recommender — no LLM, no DB, no network.

Given a customer's attributes, their current holdings, and the product catalog,
rank the products that fit (eligible and not already held), each with a
data-traceable rationale.

Inputs are plain mappings (decoupled from the ORM):
- customer: {annual_income, credit_score}
- holdings: [{product_id, status}, ...]
- products: [{product_id, name, category, min_income, min_credit_score}, ...]

Returns a list (highest fit first), each item:
    {"product_id", "name", "fit_score", "rationale"}
"""

from __future__ import annotations


def _inr(amount: float) -> str:
    return f"₹{float(amount):,.0f}"


def recommend_products(
    *,
    customer: dict,
    holdings: list[dict],
    products: list[dict],
    top_n: int = 3,
) -> list[dict]:
    income = float(customer["annual_income"])
    credit = int(customer["credit_score"])

    held_ids = {h["product_id"] for h in holdings if h.get("status", "active") == "active"}
    held_categories = {p["category"] for p in products if p["product_id"] in held_ids}

    recommendations: list[dict] = []
    for product in products:
        if product["product_id"] in held_ids:
            continue  # already holds it

        min_income = float(product["min_income"])
        min_credit = int(product["min_credit_score"])
        if income < min_income or credit < min_credit:
            continue  # not eligible

        rationale = [
            f"eligible (income {_inr(income)} ≥ {_inr(min_income)}, credit {credit} ≥ {min_credit})"
        ]

        fit = 0
        # Income headroom above the minimum.
        if min_income > 0:
            ratio = income / min_income
            fit += min(40, int((ratio - 1) * 20) + 10)
        else:
            fit += 10
        # Credit headroom above the minimum.
        fit += min(20, max(0, credit - min_credit) // 4)
        # Portfolio diversification: a category the customer doesn't yet hold.
        if product["category"] not in held_categories:
            fit += 15
            rationale.append(f"adds {product['category']} exposure not currently held")
        else:
            rationale.append(f"deepens existing {product['category']} relationship")

        recommendations.append(
            {
                "product_id": product["product_id"],
                "name": product["name"],
                "fit_score": fit,
                "rationale": "; ".join(rationale),
            }
        )

    # Highest fit first; tie-break by product_id for deterministic ordering.
    recommendations.sort(key=lambda r: (-r["fit_score"], r["product_id"]))
    return recommendations[:top_n]
