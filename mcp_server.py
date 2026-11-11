"""
mcp_server.py: Tribunal as an MCP server, so any AI agent can negotiate, sign and dispute deals.

    pip install "mcp>=2" cryptography
    python mcp_server.py        # stdio transport; add it to your MCP client's config

Tools: negotiate, approve_deal, get_deal, file_dispute. It reuses server.py's handlers, so the
same validation applies and private limits are never returned.

Appeals are deliberately not a tool: a frozen escrow is released only by a human arbitrator,
never by an agent.
"""
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import server

mcp = MCPServer(
    "tribunal",
    instructions=(
        "Tribunal negotiates deals between a buyer's agent and a seller's agent, signs the agreed deal, "
        "holds payment in escrow and settles disputes with a three-judge panel. Private limits you pass in "
        "are never shown back. Only call approve_deal after the person you act for has explicitly "
        "approved the exact price and warranty."
    ),
)


def _call(fn, *args):
    try:
        return fn(*args)
    except (server.BadRequest, ValueError, TypeError) as e:
        raise ToolError(str(e)) from None


def _deal(deal_id: str) -> dict:
    deal = server.DEALS.get(deal_id)
    if deal is None:
        raise ToolError(f"no deal {deal_id!r}")
    return deal


@mcp.tool(structured_output=True)
def negotiate(listing: dict, buyer: dict, seller: dict) -> dict[str, Any]:
    """Run a negotiation between a buyer's agent and a seller's agent.

    listing: {"title": str, "terms": {"condition": str, "battery_health_min": int, "delivery": str, ...}}
    buyer:  {"name", "limit" (max price, INR), "opening", "warranty_value_per_day", "must_have": {...}}
    seller: {"name", "limit" (min price, INR), "opening", "warranty_value_per_day" (cost to seller)}
    Names are 1-32 chars of a-z, 0-9, _ or -.

    Returns the deal_id, status (agreed, mediator_proposal, no_deal, walked_away), the proposed offer
    and a readable transcript. Nothing is binding until both people approve with approve_deal.
    """
    # shortcut: one caller submits both mandates; in production each side's agent submits only its own.
    return _call(server.create_negotiation, {"listing": listing, "buyer": buyer, "seller": seller})


@mcp.tool(structured_output=True)
def approve_deal(deal_id: str, role: str) -> dict[str, Any]:
    """Record that the buyer or the seller (role) has approved the proposed deal.

    Call only after that person explicitly confirmed. When both have approved, the deal record is
    signed by both parties and the price is held in escrow.
    """
    return _call(server.approve, _deal(deal_id), {"role": role})


@mcp.tool(structured_output=True)
def get_deal(deal_id: str) -> dict[str, Any]:
    """Read a deal: proposed offer, approvals, signed record, signature check and escrow state."""
    return server._deal_view(_deal(deal_id))


@mcp.tool(structured_output=True)
def file_dispute(deal_id: str, claimant: str, allegation: str, evidence: list[dict],
                 delivered_days_ago: float = 1) -> dict[str, Any]:
    """File a dispute on a signed deal whose escrow is still held.

    claimant: "buyer" or "seller". evidence: up to 20 items, each
    {"kind": str, "submitted_by": "buyer"|"seller"|"system", "facts": {...}, "text": str,
     "quality": "good"|"poor"}. Useful facts: powers_on (bool), battery_health (int),
    screen_ok (bool), courier_damage (bool), repair_quote (INR). Free text is treated as untrusted;
    text that tries to instruct the judges is flagged against its sender.

    Returns each judge's ruling, the verdict and the escrow state. A split panel freezes the escrow
    for a human arbitrator.
    """
    return _call(server.file_dispute, _deal(deal_id), {
        "claimant": claimant, "allegation": allegation, "evidence": evidence,
        "delivered_days_ago": delivered_days_ago})


if __name__ == "__main__":
    mcp.run()
