# Tribunal

A negotiating agent and a courthouse for agent commerce: structured offers, signed deal records, escrow instructions and a three-judge dispute panel with human appeals.

## What's here

| Path | What it is |
| --- | --- |
| `tribunal.py` | Reference implementation: mandates, strategy engine, protocol, mediator, signed deal records, escrow, Tribunal |
| `demo.py` | End-to-end demo: a laptop deal, four disputes, and a 2,000-negotiation stress test |
| `demo_output.txt` | Output of the demo |
| `test_tribunal.py` | Tests (324 cases) |
| `web/index.html` | Interactive browser demo, a self-contained page |
| `server.py` | HTTP API (standard library only); serves the pitch demo at `/` |
| `web/pitch.html` | Four-act pitch walkthrough, driven by the live API |
| `test_server.py` | API tests over real HTTP |

## Run it

```bash
pip install cryptography pytest
python demo.py
python -m pytest -q
```

Open `web/index.html` in a browser for the interactive demo.

Pitch demo on the live API:

```bash
python server.py   # then open http://localhost:8000
```

API: `POST /negotiations`, `POST /deals/{id}/approve`, `GET /deals/{id}`, `POST /deals/{id}/disputes`, `POST /cases/{id}/appeal`. Private limits stay on the server and are never returned.

## Design rules

1. Strategy is separate from language: the language layer never sees private limits.
2. Agents stop a private, random margin short of their limits, so their final offer doesn't reveal them.
3. A hard mandate guard, separate from the strategy, checks every offer and acceptance.
4. Offers trade price against warranty, so both sides can come out better off.
5. Messages are strict JSON checked against a whitelist.
6. The mediator splits at a random point inside the overlap, so it reveals neither limit.
7. Deal records are verified against an independent identity registry.
8. Judges choose from a fixed set of outcomes; refunds are the median of the majority's amounts; splits freeze escrow for a human.
9. Evidence text is untrusted. Attempts to instruct the judges are flagged and penalised.

## Related

- Product scope and pressure test: https://claude.ai/artifact/WUjyem6gLfkWE7CsPRpPnW
- Interactive demo (hosted): https://claude.ai/artifact/E4BJejeBuAQ5iYeXV2hBYp
