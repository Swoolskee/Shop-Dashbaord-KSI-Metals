#!/usr/bin/env python3
"""
Pulls every currently-open manufacturing order operation row from Katana,
buckets it into Due Today (goal: deadline is exactly today, Arizona time)
vs. Scheduled (everything else open — overdue and future), and writes an
aggregate-only JSON file for the shop-floor TV dashboard.

No customer names, order numbers, or dollar figures are written out —
only station-level counts and quantities — since this file is published
on a public GitHub Pages URL.

Requires the KATANA_API_KEY environment variable (set as a GitHub Actions
secret; never hardcode it here).
"""
import datetime
import json
import os
import sys
import time

import requests

KATANA_BASE = "https://api.katanamrp.com/v1"
API_KEY = os.environ.get("KATANA_API_KEY")
if not API_KEY:
    print("ERROR: KATANA_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Arizona has no DST — fixed UTC-7 offset year-round.
AZ_OFFSET = datetime.timedelta(hours=-7)

RESOURCE_LABELS = {
    "Load/Run Coil - Hayes": "Hayes",
    "Load/Run Coil - Snaplock": "Snaplock",
    "Break/Bend": "Bend",
    "Pull Pallets/Shear Flatsheet": "Pull Pallets/Shear",
}
UNIT_LABEL = {
    "Hayes": "linear ft",
    "Snaplock": "linear ft",
    "Bend": "pieces",
    "Pull Pallets/Shear": "pieces",
}
STATION_ORDER = ["Hayes", "Snaplock", "Bend", "Pull Pallets/Shear"]
DONE_MO_STATUSES = {"DONE", "CANCELLED"}
OPEN_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "PAUSED", "BLOCKED"]


def to_az(iso_ts: str) -> datetime.datetime:
    dt = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    return dt.astimezone(datetime.timezone(AZ_OFFSET))


def get_paginated(path: str, params: dict) -> list:
    results = []
    page = 1
    while True:
        p = dict(params, page=page, limit=250)
        resp = requests.get(f"{KATANA_BASE}{path}", headers=HEADERS, params=p, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        results.extend(data)
        if len(data) < 250:
            break
        page += 1
    return results


def batch_get_manufacturing_orders(ids: list) -> dict:
    mo_data = {}
    ids = list(ids)
    for i in range(0, len(ids), 25):
        chunk = ids[i : i + 25]
        params = [("ids[]", str(x)) for x in chunk]
        params.append(("limit", 25))
        resp = requests.get(f"{KATANA_BASE}/manufacturing_orders", headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        for mo in resp.json().get("data", []):
            mo_data[str(mo["id"])] = mo
        time.sleep(0.2)  # be polite to the API
    return mo_data


def main():
    now_az = datetime.datetime.now(datetime.timezone(AZ_OFFSET))
    today = now_az.date()

    open_rows = []
    for status in OPEN_STATUSES:
        open_rows.extend(get_paginated("/manufacturing_order_operation_rows", {"status": status}))

    tracked_rows = [r for r in open_rows if r.get("resource_name") in RESOURCE_LABELS]
    mo_ids = {str(r["manufacturing_order_id"]) for r in tracked_rows}
    mo_data = batch_get_manufacturing_orders(mo_ids)

    agg = {
        label: {"due_today": 0.0, "scheduled": 0.0, "due_today_jobs": 0, "scheduled_jobs": 0}
        for label in STATION_ORDER
    }
    skipped_stale = 0

    for row in tracked_rows:
        label = RESOURCE_LABELS[row["resource_name"]]
        mo = mo_data.get(str(row["manufacturing_order_id"]))
        if not mo:
            continue
        if mo["status"] in DONE_MO_STATUSES:
            skipped_stale += 1
            continue
        deadline_raw = mo.get("production_deadline_date")
        if not deadline_raw:
            continue
        deadline = to_az(deadline_raw).date()
        qty = mo["planned_quantity"]
        bucket = "due_today" if deadline == today else "scheduled"
        agg[label][bucket] += qty
        agg[label][f"{bucket}_jobs"] += 1

    stations = []
    for label in STATION_ORDER:
        a = agg[label]
        stations.append(
            {
                "name": label,
                "unit": UNIT_LABEL[label],
                "due_today": round(a["due_today"], 2),
                "scheduled": round(a["scheduled"], 2),
                "total": round(a["due_today"] + a["scheduled"], 2),
                "due_today_jobs": a["due_today_jobs"],
                "scheduled_jobs": a["scheduled_jobs"],
            }
        )

    output = {
        "generated_at": now_az.isoformat(),
        "target_date": today.isoformat(),
        "target_label": today.strftime("%A, %B %d"),
        "stations": stations,
        "stale_rows_excluded": skipped_stale,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "workload.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {out_path}")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
