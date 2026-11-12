"""MCP server tests: a real MCP client calls the tools, in-process and over stdio."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import Client, StdioServerParameters  # noqa: E402

import mcp_server  # noqa: E402
from test_server import BUYER, LISTING, SELLER  # noqa: E402


def run(coro):
    return asyncio.run(coro)


async def call(client, name, args):
    res = await client.call_tool(name, args)
    return res.is_error, (res.structured_content if not res.is_error else res.content[0].text)


def test_full_deal_and_dispute_over_mcp():
    async def go():
        async with Client(mcp_server.mcp) as c:
            assert {t.name for t in (await c.list_tools()).tools} == {
                "negotiate", "approve_deal", "get_deal", "file_dispute"}  # no appeal tool: humans only
            err, neg = await call(c, "negotiate", {"listing": LISTING, "buyer": BUYER, "seller": SELLER})
            assert not err and neg["offer"]
            assert "36000" not in json.dumps(neg) and '"limit"' not in json.dumps(neg)
            d = neg["deal_id"]
            _, deal = await call(c, "approve_deal", {"deal_id": d, "role": "buyer"})
            assert deal["escrow"] is None
            await call(c, "approve_deal", {"deal_id": d, "role": "seller"})
            _, deal = await call(c, "get_deal", {"deal_id": d})
            assert deal["verification"] == ["OK"] and deal["escrow"]["state"] == "held"
            err, v = await call(c, "file_dispute", {
                "deal_id": d, "claimant": "buyer", "allegation": "Does not power on.",
                "evidence": [{"kind": "unboxing_video", "submitted_by": "buyer", "facts": {"powers_on": False}},
                             {"kind": "courier_log", "submitted_by": "system", "facts": {"courier_damage": False}}]})
            assert not err and v["outcome"] == "full_refund" and v["deal"]["escrow"]["state"] == "settled"
    run(go())


def test_bad_input_is_a_tool_error():
    async def go():
        async with Client(mcp_server.mcp) as c:
            err, msg = await call(c, "negotiate", {"listing": LISTING, "buyer": {**BUYER, "opening": 40_000},
                                                   "seller": SELLER})
            assert err and "opening" in msg
            err, msg = await call(c, "get_deal", {"deal_id": "nope"})
            assert err and "no deal" in msg
    run(go())


def test_runs_as_a_stdio_process():
    params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).with_name("mcp_server.py"))])

    async def go():
        async with Client(params) as c:
            err, neg = await call(c, "negotiate", {"listing": LISTING, "buyer": BUYER, "seller": SELLER})
            assert not err and neg["status"] in ("agreed", "mediator_proposal")
    run(go())
