"""
server.py: Tribunal over HTTP (proof of concept, standard library only).

    python server.py            # http://localhost:8000  (pitch demo at /)

Endpoints (JSON in, JSON out):
    POST /negotiations                 {listing, buyer, seller}  -> transcript + proposed deal
    POST /deals/{id}/approve           {role}                    -> signed record once both approve
    GET  /deals/{id}                                             -> record, verification, escrow
    POST /deals/{id}/disputes          {claimant, allegation, evidence, delivered_days_ago}
    POST /cases/{id}/appeal            {refund_to_buyer, reasons}

Mandates (private limits) are kept server-side and never returned.
"""
import json
import random
import re
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from tribunal import (IST, ALLOWED_TERM_KEYS, Claim, Escrow, Evidence, Mandate, NegotiatingAgent, Party,
                      ProportionalJudge, SkepticJudge, TextualistJudge, Tribunal, close_deal, mediate,
                      negotiate, render_for_humans)

WEB = Path(__file__).parent / "web"
MAX_BODY = 64 * 1024

# shortcut: in-memory state and server-held signing keys; move to a database and per-user key custody
# (wallet/HSM) before anyone but a demo depends on it.
REGISTRY: dict[str, str] = {}
PARTIES: dict[str, Party] = {}
DEALS: dict[str, dict] = {}
CASES: dict[str, str] = {}  # case_id -> deal_id
TRIBUNAL = Tribunal([TextualistJudge("judge-a", "provider-a"),
                     ProportionalJudge("judge-b", "provider-b"),
                     SkepticJudge("judge-c", "provider-c")], REGISTRY)
_NAME = re.compile(r"[a-z0-9_-]{1,32}")


class BadRequest(Exception):
    pass


def _party(name, role) -> Party:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise BadRequest("party name must be 1-32 chars of a-z, 0-9, _ or -")
    p = PARTIES.get(name)
    if p is None:
        p = PARTIES[name] = Party(name, role)
        REGISTRY[name] = p.public_key_hex
    elif p.role != role:
        raise BadRequest(f"{name!r} is already registered as a {p.role}")
    return p


def _mandate(role, d: dict) -> Mandate:
    if not isinstance(d, dict):
        raise BadRequest(f"{role} must be an object")
    must = d.get("must_have", {})
    if not isinstance(must, dict) or not set(must) <= ALLOWED_TERM_KEYS:
        raise BadRequest(f"must_have keys must be a subset of {sorted(ALLOWED_TERM_KEYS)}")
    try:
        return Mandate(role, int(d["limit"]), int(d["opening"]), float(d.get("warranty_value_per_day", 0)),
                       must_have=must)
    except KeyError as e:
        raise BadRequest(f"{role}.{e.args[0]} is required") from None


def _deal_view(deal: dict) -> dict:
    rec, esc = deal["record"], deal["escrow"]
    return {"deal_id": deal["deal_id"], "status": deal["status"], "offer": deal["offer"],
            "approved_by": sorted(deal["approved"]),
            "record": json.loads(rec.export()) if rec else None,
            "verification": (rec.verify(REGISTRY) or ["OK"]) if rec else None,
            "escrow": {"state": esc.state, "amount": esc.amount, "to_buyer": esc.to_buyer,
                       "to_seller": esc.to_seller, "log": esc.log} if esc else None}


def _verdict_view(v) -> dict:
    return {"case_id": v.case_id, "status": v.status, "outcome": v.outcome, "refund_amount": v.refund_amount,
            "tally": v.tally, "notes": v.notes,
            "rulings": [{"judge": r.judge, "provider": r.provider, "outcome": r.outcome,
                         "refund_amount": r.refund_amount, "reasons": r.reasons} for r in v.rulings]}


def create_negotiation(body: dict) -> dict:
    listing = body.get("listing")
    if not isinstance(listing, dict) or not isinstance(listing.get("terms", {}), dict):
        raise BadRequest("listing must be an object with a terms object")
    if not set(listing.get("terms", {})) <= ALLOWED_TERM_KEYS:
        raise BadRequest(f"listing.terms keys must be a subset of {sorted(ALLOWED_TERM_KEYS)}")
    buyer = _party(body.get("buyer", {}).get("name", "buyer"), "buyer")
    seller = _party(body.get("seller", {}).get("name", "seller"), "seller")
    bm, sm = _mandate("buyer", body.get("buyer")), _mandate("seller", body.get("seller"))
    deal_id = "d_" + uuid.uuid4().hex[:8]
    rng = random.Random()
    res = negotiate(NegotiatingAgent(bm, rng=rng),
                    NegotiatingAgent(sm, listing_terms=listing.get("terms", {}), rng=rng), deal_id,
                    mediator=lambda t, k: mediate(bm, sm, t, deal_id, k, rng))
    DEALS[deal_id] = {"deal_id": deal_id, "status": res.status, "result": res, "listing": listing,
                      "buyer": buyer, "seller": seller, "approved": set(), "record": None, "escrow": None,
                      "offer": res.offer.to_dict() if res.offer else None}
    return {"deal_id": deal_id, "status": res.status, "messages": res.messages,
            "offer": DEALS[deal_id]["offer"],
            "transcript": [{**e, "text": render_for_humans(e)} for e in res.transcript]}


def approve(deal: dict, body: dict) -> dict:
    role = body.get("role")
    if role not in ("buyer", "seller"):
        raise BadRequest("role must be buyer or seller")
    if deal["offer"] is None:
        raise BadRequest("no deal to approve")
    deal["approved"].add(role)
    if deal["approved"] == {"buyer", "seller"} and deal["record"] is None:
        deal["record"] = close_deal(deal["result"], deal["buyer"], deal["seller"], deal["listing"],
                                    approve=lambda r, o: True)
        deal["escrow"] = Escrow(deal["deal_id"], deal["record"].body["price"])
        deal["status"] = "signed"
    return _deal_view(deal)


def _evidence(i, e) -> Evidence:
    if not isinstance(e, dict) or not isinstance(e.get("facts", {}), dict):
        raise BadRequest(f"evidence[{i}] must be an object with a facts object")
    if e.get("submitted_by") not in ("buyer", "seller", "system"):
        raise BadRequest(f"evidence[{i}].submitted_by must be buyer, seller or system")
    if e.get("quality", "good") not in ("good", "poor"):
        raise BadRequest(f"evidence[{i}].quality must be good or poor")
    return Evidence(str(e.get("id", f"e{i + 1}"))[:16], str(e.get("kind", "other"))[:32], e["submitted_by"],
                    e.get("facts", {}), str(e.get("text", ""))[:2000], e.get("quality", "good"))


def file_dispute(deal: dict, body: dict) -> dict:
    if deal["escrow"] is None:
        raise BadRequest("deal is not signed yet")
    if deal["escrow"].state != "held":
        raise BadRequest(f"escrow is already {deal['escrow'].state}")
    if body.get("claimant") not in ("buyer", "seller"):
        raise BadRequest("claimant must be buyer or seller")
    evidence = body.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) > 20:
        raise BadRequest("evidence must be a list of at most 20 items")
    delivered = datetime.now(IST) - timedelta(days=float(body.get("delivered_days_ago", 1)))
    v = TRIBUNAL.hear(Claim(deal["record"], body["claimant"], str(body.get("allegation", ""))[:2000],
                            [_evidence(i, e) for i, e in enumerate(evidence)], delivered), deal["escrow"])
    CASES[v.case_id] = deal["deal_id"]
    return {**_verdict_view(v), "deal": _deal_view(deal)}


def appeal(case_id: str, body: dict) -> dict:
    if case_id not in TRIBUNAL.human_queue:
        raise BadRequest("case is not awaiting a human")
    deal = DEALS[CASES[case_id]]
    refund = body.get("refund_to_buyer")
    if not isinstance(refund, int) or isinstance(refund, bool) or not 0 <= refund <= deal["escrow"].amount:
        raise BadRequest(f"refund_to_buyer must be an integer from 0 to {deal['escrow'].amount}")
    v = TRIBUNAL.resolve_appeal(case_id, refund, str(body.get("reasons", ""))[:2000])
    return {**_verdict_view(v), "deal": _deal_view(deal)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self, method):
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        try:
            if method == "GET" and not parts:
                return self._send(200, (WEB / "pitch.html").read_bytes(), "text/html; charset=utf-8")
            if method == "GET" and parts == ["playground"]:
                return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
            if method == "GET" and len(parts) == 2 and parts[0] == "deals" and parts[1] in DEALS:
                return self._send(200, _deal_view(DEALS[parts[1]]))
            if method != "POST":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._send(413, {"error": "body too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise BadRequest("body must be a JSON object")
            if parts == ["negotiations"]:
                return self._send(201, create_negotiation(body))
            if len(parts) == 3 and parts[0] == "deals" and parts[1] in DEALS:
                if parts[2] == "approve":
                    return self._send(200, approve(DEALS[parts[1]], body))
                if parts[2] == "disputes":
                    return self._send(201, file_dispute(DEALS[parts[1]], body))
            if len(parts) == 3 and parts[0] == "cases" and parts[2] == "appeal":
                return self._send(200, appeal(parts[1], body))
            return self._send(404, {"error": "not found"})
        except json.JSONDecodeError:
            return self._send(400, {"error": "invalid JSON"})
        except (BadRequest, ValueError, TypeError) as e:  # Mandate/Evidence validation raises ValueError
            return self._send(400, {"error": str(e)})
        except Exception as e:  # never leave the client hanging
            self.log_error("unhandled: %r", e)
            return self._send(500, {"error": "internal error"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Tribunal API on http://localhost:{port}")
    # Single-threaded on purpose: the in-memory state has no locks.
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
