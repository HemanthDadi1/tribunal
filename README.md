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
| `web/simulation.html` | Live animated market simulation: the same agent market runs side by side, today's dispute handling vs Tribunal |

## Run it

```bash
pip install cryptography pytest
python demo.py
python -m pytest -q
```

Open `web/index.html` in a browser for the interactive demo.

## Live demo

The interactive demo is published to GitHub Pages from `web/` on every push to `main`:
https://hemanthdadi1.github.io/tribunal/ (simulation: https://hemanthdadi1.github.io/tribunal/simulation.html)

One-time setup: in the repo's Settings → Pages, set **Source** to **GitHub Actions**.

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
