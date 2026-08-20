"""Playwright check: the monitor loads the right view per system type.

Starts the mock daemon in a thread, drives the real page in Chromium, and asserts
the behaviour the operator asked for:

  - an AI system's Training button shows the MODEL CARD (formation, not a curve),
  - its 2026 button still shows a real forward BACKTEST,
  - a traditional system's Training shows a backtest, never a model card,
  - the system type is labelled in the rail and the detail.

Run: python research/system06/preview/test_frontend.py
"""

from __future__ import annotations

import sys
import threading
import time
from http.server import ThreadingHTTPServer

from playwright.sync_api import expect, sync_playwright

import mock_server

PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"


def _serve():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), mock_server.Handler)
    server.serve_forever()


def main() -> int:
    threading.Thread(target=_serve, daemon=True).start()
    time.sleep(0.6)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE, wait_until="networkidle")

        # The rail renders one card per hypothesis (the 2026 half).
        page.wait_for_selector('.card[data-id="s06-fwd"]', timeout=8000)

        # 1) The rail labels the system's type.
        expect(page.locator('.card[data-id="s06-fwd"] .typechip.ai-model')).to_have_text("AI model")

        # 2) Open the AI system -> its 2026 forward is a real backtest (has Equity).
        page.locator('.card[data-id="s06-fwd"]').first.click()
        expect(page.locator("#detail .typechip.ai-model")).to_be_visible()
        expect(page.get_by_role("heading", name="Equity · 2026")).to_be_visible()
        assert page.get_by_text("Model formation").count() == 0, "2026 must be a backtest, not the model card"

        # 3) Press Training -> the MODEL CARD, not a backtest curve.
        page.locator('#detail .phase button[data-era="training"]').click()
        expect(page.get_by_text("Model formation").first).to_be_visible(timeout=6000)
        expect(page.get_by_text("Val accuracy")).to_be_visible()
        expect(page.get_by_text("Architecture")).to_be_visible()
        assert page.get_by_role("heading", name="Equity · training").count() == 0, "AI training must not show an equity panel"
        assert page.locator("#detail .mcard .spark").count() == 1, "loss-curve sparkline missing"

        # 4) Back to 2026 -> backtest again.
        page.locator('#detail .phase button[data-era="2026"]').click()
        expect(page.get_by_role("heading", name="Equity · 2026")).to_be_visible(timeout=6000)

        # 5) A traditional system: Training is a backtest, never a model card.
        page.locator('.card[data-from="champion"][data-id="trad-fwd"]').first.click()
        expect(page.locator("#detail .typechip.traditional")).to_be_visible()
        page.locator('#detail .phase button[data-era="training"]').click()
        expect(page.get_by_role("heading", name="Equity · training")).to_be_visible(timeout=6000)
        assert page.get_by_text("Model formation").count() == 0, "a traditional system must never show a model card"

        browser.close()
        if errors:
            print("PAGE ERRORS:", *errors, sep="\n  ")
            return 1

    print("\nALL FRONTEND CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
