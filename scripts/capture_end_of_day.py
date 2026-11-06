#!/usr/bin/env python3
"""Capture a dated 4 PM Arizona screenshot from freshly refreshed local board data."""
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
data = json.loads((root / "docs/dashboard-data.json").read_text())
today = dt.datetime.now(ZoneInfo("America/Phoenix")).date().isoformat()
if data.get("businessDate") != today:
    raise SystemExit(f"Refusing stale screenshot: data date {data.get('businessDate')} != {today}")
generated = dt.datetime.fromisoformat(data["generatedAt"].replace("Z", "+00:00"))
age = (dt.datetime.now(dt.timezone.utc) - generated).total_seconds()
if age < 0 or age > 15 * 60:
    raise SystemExit(f"Refusing stale screenshot: generatedAt age {age:.0f} seconds")

destination = root / "docs" / "end-of-day" / f"{today}.png"
destination.parent.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    page.goto("http://127.0.0.1:8765/", wait_until="networkidle", timeout=30000)
    page.locator(".connection-live").wait_for(timeout=15000)
    page.locator(".station-card").first.wait_for(timeout=15000)
    if page.locator(".station-card").count() != 4:
        raise SystemExit("Dashboard did not render all four stations")
    page.screenshot(path=str(destination), full_page=True, animations="disabled")
    browser.close()
print(f"Screenshot saved: {destination}")
with open(os.environ["GITHUB_OUTPUT"], "a") as output:
    print(f"image_path={destination.relative_to(root)}", file=output)
    print(f"business_date={today}", file=output)
