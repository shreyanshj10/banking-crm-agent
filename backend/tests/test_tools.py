"""DB-backed tests for the LLM-facing tools (run against the seeded database).

Covers the batch scoring tool contract and the query_customers default limit.
"""

import pytest

from app.tools.data_tools import query_customers
from app.tools.scoring_tool import score_customers

pytestmark = pytest.mark.asyncio


async def test_score_customers_ranked_descending():
    # A mix of strong / weak / ineligible ids — result must be ranked by score desc.
    ids = ["C00025", "C00040", "C00016", "C00059"]
    rows = await score_customers.ainvoke({"customer_ids": ids, "product_id": "PL001"})

    assert isinstance(rows, list) and len(rows) == len(ids)
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True), scores
    for r in rows:
        assert {"customer_id", "product_id", "score", "band", "reasons"} <= set(r), r


async def test_score_customers_single_id_returns_one_ranked_result():
    rows = await score_customers.ainvoke({"customer_ids": ["C00040"], "product_id": "PL001"})

    assert isinstance(rows, list) and len(rows) == 1
    assert rows[0]["customer_id"] == "C00040"
    assert "score" in rows[0] and "band" in rows[0] and rows[0]["reasons"]


async def test_query_customers_default_limit_applies_and_is_overridable():
    # 60 customers are seeded; with no limit the tool caps the result set.
    default_rows = await query_customers.ainvoke({})
    assert len(default_rows) == 25, len(default_rows)

    capped = await query_customers.ainvoke({"limit": 5})
    assert len(capped) == 5, len(capped)


async def test_holds_product_id_keeps_only_active_holders():
    # holds_product_id (EXISTS) is the exact complement of exclude_product_id
    # (NOT EXISTS) on the same data: every customer either actively holds PL001
    # or doesn't, with no overlap.
    big = 1000
    holders = await query_customers.ainvoke({"holds_product_id": "PL001", "limit": big})
    non_holders = await query_customers.ainvoke({"exclude_product_id": "PL001", "limit": big})
    everyone = await query_customers.ainvoke({"limit": big})

    holder_ids = {c["id"] for c in holders}
    non_ids = {c["id"] for c in non_holders}
    all_ids = {c["id"] for c in everyone}

    assert holder_ids, "expected some active PL001 holders in the seed"
    assert holder_ids.isdisjoint(non_ids), "a customer can't be both a holder and a non-holder"
    assert holder_ids | non_ids == all_ids, "holders + non-holders must partition the whole book"
