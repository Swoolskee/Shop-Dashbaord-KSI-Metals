#!/usr/bin/env python3
"""Refresh the Prod KSI floor dashboard from Katana.

Rules:
- America/Phoenix business day.
- First successful run of a new day snapshots Goal Today.
- Later same-day runs preserve Goal Today exactly.
- Current, Can Produce, top operators, remaining, and Created Orders stay live.
- Only aggregate station data is written to docs/dashboard-data.json.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

BASE_URL = "https://api.katanamrp.com/v1"
API_KEY = (os.environ.get("KATANA_API_KEY") or "").strip()
if not API_KEY:
    print("ERROR: KATANA_API_KEY is not set", file=sys.stderr)
    sys.exit(1)

# GitHub secret should normally contain only the raw Katana API token.
# Be forgiving if someone pasted "Bearer <token>" instead.
if API_KEY.lower().startswith("bearer "):
    API_KEY = API_KEY[7:].strip()

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}
AZ = dt.timezone(dt.timedelta(hours=-7))
OPEN_STATUSES = ("NOT_STARTED", "IN_PROGRESS", "PAUSED", "BLOCKED")
PAGE_SIZE = 100
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "dashboard-data.json"

STATIONS = [
    {"id": "hayes", "name": "Hayes", "shortName": "HY", "unit": "LF"},
    {"id": "snaplock", "name": "Snaplock", "shortName": "SN", "unit": "LF"},
    {"id": "bend", "name": "Bend", "shortName": "BD", "unit": "PCS"},
    {"id": "pull-shear", "name": "Pull Pallets / Shear", "shortName": "PS", "unit": "PCS"},
]

RESOURCE_TO_STATION = {
    "Load/Run Coil - Hayes": "hayes",
    "Load/Run Coil - Snaplock": "snaplock",
    "Load/Run Coil - Snap Lock": "snaplock",
    "Break/Bend": "bend",
    "Pull Pallets/Shear Flatsheet": "pull-shear",
}


def request_json(path: str, params=None):
    url = f"{BASE_URL}{path}"
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=45)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Katana request failed: {url}: {last_error}")


def get_paginated(path: str, params=None):
    params = dict(params or {})
    rows = []
    page = 1
    while True:
        page_params = dict(params)
        page_params.update({"page": page, "limit": PAGE_SIZE})
        data = request_json(path, page_params).get("data", [])
        rows.extend(data)
        if len(data) < PAGE_SIZE:
            break
        page += 1
    return rows


def batch_manufacturing_orders(ids):
    ids = list(dict.fromkeys(int(x) for x in ids))
    result = {}
    for offset in range(0, len(ids), 40):
        chunk = ids[offset : offset + 40]
        params = [("ids", str(x)) for x in chunk] + [("limit", "100"), ("page", "1")]
        data = request_json("/manufacturing_orders", params).get("data", [])
        for mo in data:
            result[int(mo["id"])] = mo
        if len(data) != len(chunk):
            missing = sorted(set(chunk) - set(result))
            if missing:
                raise RuntimeError(f"Missing manufacturing orders from Katana response: {missing}")
        time.sleep(0.1)
    return result


def parse_utc(value: str):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def az_date(value: str):
    return parse_utc(value).astimezone(AZ).date()


def remaining_quantity(mo):
    value = mo.get("remaining_quantity")
    if value is None:
        planned = mo.get("planned_quantity")
        completed = mo.get("completed_quantity")
        if planned is not None and completed is not None:
            value = float(planned) - float(completed)
        else:
            value = planned
    if value is None:
        raise RuntimeError(f"MO {mo.get('id')} has no usable remaining quantity")
    return max(float(value), 0.0)


def top_operator(operator_qty):
    if not operator_qty:
        return "-", 0
    name, qty = sorted(operator_qty.items(), key=lambda item: (-item[1], item[0]))[0]
    return name, qty


def validate_auth():
    try:
        request_json("/manufacturing_order_operation_rows", {"limit": 1, "page": 1})
    except RuntimeError as exc:
        print("ERROR: Katana authentication failed.", file=sys.stderr)
        print("Check the GitHub Actions secret named KATANA_API_KEY.", file=sys.stderr)
        print("It must contain a valid Katana API token (raw token preferred; do not use an MCP login token).", file=sys.stderr)
        raise


def main():
    validate_auth()
    now_az = dt.datetime.now(AZ)
    today = now_az.date()
    tomorrow = today + dt.timedelta(days=1)
    start_utc = dt.datetime.combine(today, dt.time.min, tzinfo=AZ).astimezone(dt.timezone.utc)
    end_utc = dt.datetime.combine(tomorrow, dt.time.min, tzinfo=AZ).astimezone(dt.timezone.utc)

    previous = {}
    if OUTPUT_PATH.exists():
        try:
            previous = json.loads(OUTPUT_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            previous = {}

    completed_candidates = get_paginated(
        "/manufacturing_order_operation_rows",
        {"status": "COMPLETED", "updated_at_min": start_utc.isoformat().replace("+00:00", "Z")},
    )
    completed_rows = [
        row
        for row in completed_candidates
        if row.get("resource_name") in RESOURCE_TO_STATION
        and row.get("completed_at")
        and start_utc <= parse_utc(row["completed_at"]) < end_utc
        and row.get("completed_by_operators")
    ]

    open_rows = []
    for status in OPEN_STATUSES:
        open_rows.extend(get_paginated("/manufacturing_order_operation_rows", {"status": status}))
    open_rows = [row for row in open_rows if row.get("resource_name") in RESOURCE_TO_STATION]

    mo_ids = {row["manufacturing_order_id"] for row in completed_rows + open_rows}
    mo_map = batch_manufacturing_orders(mo_ids)

    current = defaultdict(float)
    completed_mos = defaultdict(set)
    operator_qty = defaultdict(lambda: defaultdict(float))

    for row in completed_rows:
        station = RESOURCE_TO_STATION[row["resource_name"]]
        mo = mo_map.get(int(row["manufacturing_order_id"]))
        if not mo:
            raise RuntimeError(f"Missing MO {row['manufacturing_order_id']} for completed row")

        mo_id = int(mo["id"])
        qty = float(mo.get("planned_quantity") or 0)
        if mo_id not in completed_mos[station]:
            completed_mos[station].add(mo_id)
            current[station] += qty

        operators = row["completed_by_operators"]
        share = qty / len(operators)
        for operator in operators:
            operator_qty[station][operator["name"]] += share

    due_qty = defaultdict(float)
    due_mos = defaultdict(set)
    all_open_qty = defaultdict(float)
    all_open_mos = defaultdict(set)

    for row in open_rows:
        station = RESOURCE_TO_STATION[row["resource_name"]]
        mo = mo_map.get(int(row["manufacturing_order_id"]))
        if not mo:
            raise RuntimeError(f"Missing MO {row['manufacturing_order_id']} for open row")

        mo_id = int(mo["id"])
        qty = remaining_quantity(mo)

        if mo_id not in all_open_mos[station]:
            all_open_mos[station].add(mo_id)
            all_open_qty[station] += qty

        deadline_raw = mo.get("sales_order_delivery_deadline") or mo.get("production_deadline_date")
        if deadline_raw and az_date(deadline_raw) <= today and mo_id not in due_mos[station]:
            due_mos[station].add(mo_id)
            due_qty[station] += qty

    created_orders = get_paginated(
        "/sales_orders",
        {
            "created_at_min": start_utc.isoformat().replace("+00:00", "Z"),
            "created_at_max": end_utc.isoformat().replace("+00:00", "Z"),
        },
    )
    created_orders = [order for order in created_orders if not order.get("deleted_at")]

    previous_stations = {row["id"]: row for row in previous.get("stations", [])}
    new_business_day = previous.get("businessDate") != today.isoformat()

    stations = []
    for meta in STATIONS:
        sid = meta["id"]
        cur = current[sid]
        if new_business_day:
            goal = cur + due_qty[sid]
        else:
            if sid not in previous_stations:
                raise RuntimeError(f"Existing dashboard is missing station {sid}")
            goal = float(previous_stations[sid]["goal"])

        top_name, top_qty = top_operator(operator_qty[sid])
        station = {
            **meta,
            "current": cur,
            "goal": goal,
            "canProduce": cur + all_open_qty[sid],
            "remaining": max(goal - cur, 0),
            "completedJobs": len(completed_mos[sid]),
            "goalJobs": len(completed_mos[sid] | due_mos[sid]),
            "topOperator": top_name,
            "topOperatorQuantity": top_qty,
        }
        stations.append(station)

    summary = {
        "current": sum(s["current"] for s in stations),
        "goal": sum(s["goal"] for s in stations),
        "canProduce": sum(s["canProduce"] for s in stations),
        "remaining": sum(s["remaining"] for s in stations),
        "completedJobs": sum(s["completedJobs"] for s in stations),
        "goalJobs": sum(s["goalJobs"] for s in stations),
        "createdOrders": len(created_orders),
    }

    output = {
        "businessDate": today.isoformat(),
        "businessDateLabel": today.strftime("%A, %B %-d").upper(),
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "timeZone": "America/Phoenix",
        "stations": stations,
        "summary": summary,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    print("Goal snapshot:", "NEW DAY" if new_business_day else "PRESERVED")


if __name__ == "__main__":
    main()
