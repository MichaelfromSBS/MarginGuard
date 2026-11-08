"""Observed sales and modeled replacement costs. No model calls or SQL floats."""
from collections import Counter, defaultdict
from contextvars import ContextVar
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from .errors import DomainError
from .ingestion import now, restaurant_record

ZERO = Decimal("0")
demo_clock = ContextVar("marginguard_demo_date", default=None)
PRECISION = Decimal("0.00000001")
CENT = Decimal("0.01")
SALES_ASSUMPTIONS = [
    "Observed approved completed receipts only; missing receipts are not estimated.",
    "Net item revenue includes allocated item discounts and excludes tax and tips; it is not payout or profit.",
    "Void/refund documents are not modeled as completed sales; unresolved documents are excluded.",
    "Receipt local dates use the restaurant timezone. Evidence is a bounded sample, not an exhaustive source list.",
]
COST_ASSUMPTIONS = [
    "Replacement ingredient cost uses approved prices effective on or before the as-of date.",
    "Ingredient costs exclude freight, purchase tax, waste, inventory, labor and rent; they are not actual COGS or profit.",
    "Channel contribution assumes configured menu prices, fee rates and packaging only; demand response is not modeled.",
]


def decimal_text(value, *, money=False):
    result = Decimal(value).quantize(CENT if money else PRECISION, rounding=ROUND_HALF_UP)
    if not result:
        result = abs(result)  # Avoid signed zero in wire contracts.
    text = format(result, "f")
    return text if money else text.rstrip("0").rstrip(".")


def local_today(owner):
    if owner.get("is_demo") and demo_clock.get() is not None:
        return demo_clock.get()
    return datetime.now(ZoneInfo(owner["timezone"])).date()


def dates(start, end):
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def period_dates(owner, start=None, end=None, as_of=None):
    as_of = as_of or local_today(owner)
    if not 1900 <= as_of.year <= 9998:
        raise DomainError("invalid_period", "As-of year must be between 1900 and 9998.", 422)
    # Live observed metrics include today's approved receipts. Forecast training
    # and yesterday's anomaly checks select their finished-day ranges separately.
    end = end or as_of
    start = start or end - timedelta(days=6)
    if end < start or (end - start).days >= 366:
        raise DomainError("invalid_period", "Choose an ordered period of at most 366 days.", 422)
    if end > as_of:
        raise DomainError("invalid_period", "Sales period cannot extend beyond the as-of date.", 422)
    return start, end, as_of


def coverage_summary(conn, start, end, channels=None):
    channels = channels if channels is not None else [r[0] for r in conn.execute("SELECT id FROM channels ORDER BY id")]
    saved = {(r["date"], r["channel_id"]): dict(r) for r in conn.execute(
        "SELECT * FROM daily_coverage WHERE date BETWEEN ? AND ?", (start.isoformat(), end.isoformat()))}
    calendar = {r["date"]: r["is_open"] for r in conn.execute(
        "SELECT date,is_open FROM restaurant_calendar WHERE date BETWEEN ? AND ?", (start.isoformat(), end.isoformat()))}
    rows = []
    stamp = now()
    for day in dates(start, end):
        for channel in channels:
            key = (day.isoformat(), channel)
            row = saved.get(key, {"date": key[0], "channel_id": channel, "status": "unknown", "updated_at": stamp}).copy()
            # Explicit closure has priority; inconsistent sales are caught below.
            if calendar.get(key[0]) == 0:
                row["status"] = "closed"
            rows.append(row)
    sold = {(r["local_date"], r["channel_id"]) for r in conn.execute(
        """SELECT DISTINCT r.local_date,r.channel_id FROM receipts r JOIN documents d ON d.id=r.document_id
           WHERE r.local_date BETWEEN ? AND ? AND r.status='completed' AND d.status='completed'""",
        (start.isoformat(), end.isoformat()))}
    for row in rows:
        if row["status"] == "closed" and (row["date"], row["channel_id"]) in sold:
            row["status"] = "partial"
    counts = Counter(r["status"] for r in rows)
    state = "complete" if rows and not (counts["partial"] or counts["unknown"]) else "partial" if counts["complete"] or counts["partial"] or counts["closed"] else "unknown"
    return {"period": {"start": start, "end": end}, **{s: counts[s] for s in ["complete", "partial", "unknown", "closed"]}, "status": state, "days": rows}


def sales_rows(conn, start, end):
    return [dict(r) for r in conn.execute(
        """SELECT i.*,r.id AS receipt_id,r.document_id,r.channel_id,r.local_date,r.sold_at
           FROM receipt_items i JOIN receipts r ON r.id=i.receipt_id
           JOIN documents d ON d.id=r.document_id
           WHERE r.local_date BETWEEN ? AND ? AND r.status='completed' AND d.status='completed'
           AND r.currency='USD' ORDER BY r.local_date,r.sold_at,r.id,i.id""", (start.isoformat(), end.isoformat()))]


def evidence(row, kind="receipt_item"):
    return {"kind": kind, "record_id": row["id"], "document_id": row["document_id"],
            "source_page": row["source_page"], "quote": row["source_text"]}


def sales_summary(conn, start, end, *, dish_id=None, channel_id=None):
    owner = restaurant_record(conn)
    for table, value, code in [("dishes", dish_id, "dish_not_found"), ("channels", channel_id, "channel_not_found")]:
        if value and not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (value,)).fetchone():
            raise DomainError(code, "Requested catalog entry does not exist.", 404)
    rows = [r for r in sales_rows(conn, start, end) if (not dish_id or r["dish_id"] == dish_id) and (not channel_id or r["channel_id"] == channel_id)]

    def aggregate(values, **key):
        return {**key, "units": decimal_text(sum((Decimal(r["quantity"]) for r in values), ZERO)),
                "net_revenue": decimal_text(sum((Decimal(r["net_amount"]) for r in values), ZERO), money=True),
                "orders": len({r["receipt_id"] for r in values})}

    def groups(field):
        grouped = defaultdict(list)
        for row in rows:
            grouped[row[field]].append(row)
        return [aggregate(values, **{("date" if field == "local_date" else field): key}) for key, values in sorted(grouped.items())]

    total = aggregate(rows)
    return {"period": {"start": start, "end": end}, "as_of": now(), "source_data_version": owner["data_version"],
            **total, "average_order_revenue": decimal_text(Decimal(total["net_revenue"]) / total["orders"], money=True) if total["orders"] else None,
            "coverage": coverage_summary(conn, start, end, [channel_id] if channel_id else None),
            "by_day": groups("local_date"), "by_dish": groups("dish_id"), "by_channel": groups("channel_id"),
            "evidence": [evidence(r) for r in rows[:20]], "evidence_truncated": len(rows) > 20,
            "assumptions": SALES_ASSUMPTIONS + (["Dish-filtered order count counts each matching receipt once; it is not additive across dishes."] if dish_id else [])}


def base_quantity(quantity, unit, base_unit):
    quantity = Decimal(quantity)
    if unit == base_unit:
        return quantity
    if unit == "oz" and base_unit == "lb":
        return quantity / 16
    if unit == "lb" and base_unit == "oz":
        return quantity * 16
    raise ValueError("Recipe and ingredient units are incompatible.")


def menu_price(conn, dish_id, channel_id, as_of):
    return conn.execute("""SELECT * FROM menu_prices WHERE dish_id=? AND channel_id=? AND effective_date<=?
                           ORDER BY effective_date DESC,id DESC LIMIT 1""", (dish_id, channel_id, as_of.isoformat())).fetchone()


def dish_cost(conn, dish_id, as_of):
    dish = conn.execute("SELECT * FROM dishes WHERE id=?", (dish_id,)).fetchone()
    if dish is None:
        raise DomainError("dish_not_found", "Dish does not exist.", 404)
    recipe = conn.execute("SELECT * FROM recipe_versions WHERE dish_id=? AND effective_date<=? ORDER BY effective_date DESC,id DESC LIMIT 1", (dish_id, as_of.isoformat())).fetchone()
    lines, limitations, raw_cost = [], [], ZERO
    if recipe is None:
        limitations.append("No effective recipe is configured for this dish.")
    else:
        items = conn.execute("""SELECT ri.*,i.name,i.base_unit FROM recipe_items ri JOIN ingredients i ON i.id=ri.ingredient_id
                              WHERE recipe_version_id=? ORDER BY ingredient_id""", (recipe["id"],)).fetchall()
        if not items:
            limitations.append("The selected recipe has no ingredients.")
        for item in items:
            try:
                quantity = base_quantity(item["quantity"], item["unit"], item["base_unit"])
            except ValueError:
                limitations.append(f"Incompatible recipe units for {item['ingredient_id']}.")
                continue
            price = conn.execute("""SELECT p.*,l.source_page,l.source_text,v.document_id FROM ingredient_prices p
                JOIN invoice_lines l ON l.id=p.invoice_line_id JOIN invoices v ON v.id=l.invoice_id
                JOIN documents d ON d.id=v.document_id WHERE p.ingredient_id=? AND p.effective_date<=?
                AND d.status='completed' AND v.currency='USD'
                ORDER BY p.effective_date DESC,d.created_at DESC,p.rowid DESC LIMIT 1""", (item["ingredient_id"], as_of.isoformat())).fetchone()
            if price is None or price["base_unit"] != item["base_unit"]:
                limitations.append(f"No compatible approved price for {item['ingredient_id']}.")
                price = None
            extended = quantity * Decimal(price["unit_cost"]) if price else None
            if extended is not None:
                raw_cost += extended
            reference = evidence({**dict(price), "id": price["invoice_line_id"]}, "invoice_line") if price else None
            lines.append({"ingredient_id": item["ingredient_id"], "name": item["name"], "quantity": decimal_text(quantity),
                          "base_unit": item["base_unit"], "unit_cost": price["unit_cost"] if price else None,
                          "extended_cost": decimal_text(extended) if extended is not None else None,
                          "price_effective_date": price["effective_date"] if price else None, "evidence": reference})
    channels = []
    for channel in conn.execute("SELECT * FROM channels ORDER BY id"):
        price = menu_price(conn, dish_id, channel["id"], as_of)
        contribution = Decimal(price["price"]) * (1 - Decimal(channel["fee_rate"])) - Decimal(channel["packaging_cost"]) - raw_cost if price and not limitations else None
        channels.append({"channel_id": channel["id"], "menu_price": price["price"] if price else None,
                         "menu_price_id": price["id"] if price else None, "fee_rate": channel["fee_rate"], "packaging_cost": channel["packaging_cost"],
                         "contribution": decimal_text(contribution, money=True) if contribution is not None else None,
                         "contribution_margin_pct": decimal_text(contribution / Decimal(price["price"]) * 100) if contribution is not None and Decimal(price["price"]) else None})
    return {"dish_id": dish_id, "name": dish["name"], "as_of": as_of, "source_data_version": restaurant_record(conn)["data_version"],
            "assumptions": COST_ASSUMPTIONS, "recipe_version_id": recipe["id"] if recipe else None,
            "ingredient_cost": decimal_text(raw_cost, money=True) if not limitations else None,
            "ingredients": lines, "channels": channels, "limitations": limitations}


def complete_coverage(conn, body):
    owner = restaurant_record(conn)
    if not conn.execute("SELECT 1 FROM channels WHERE id=?", (body.channel_id,)).fetchone():
        raise DomainError("channel_not_found", "Channel does not exist.", 404)
    if body.status == "complete" and body.date >= local_today(owner):
        raise DomainError("day_not_finished", "Only finished local days can be marked complete.", 409)
    sold = conn.execute("SELECT 1 FROM receipts WHERE local_date=? AND channel_id=? AND status='completed' LIMIT 1", (body.date.isoformat(), body.channel_id)).fetchone()
    calendar = conn.execute("SELECT is_open FROM restaurant_calendar WHERE date=?", (body.date.isoformat(),)).fetchone()
    if body.status == "closed" and sold:
        raise DomainError("closed_day_has_sales", "A day/channel with approved sales cannot be marked closed.", 409)
    if body.status == "complete" and calendar and not calendar["is_open"]:
        raise DomainError("calendar_conflict", "The business calendar marks this date closed. Review the calendar before confirming sales coverage.", 409)
    previous = conn.execute("SELECT * FROM daily_coverage WHERE date=? AND channel_id=?", (body.date.isoformat(), body.channel_id)).fetchone()
    if previous and previous["status"] == body.status:
        return dict(previous)
    stamp = now()
    conn.execute("""INSERT INTO daily_coverage(date,channel_id,status,updated_at) VALUES (?,?,?,?)
        ON CONFLICT(date,channel_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at""",
        (body.date.isoformat(), body.channel_id, body.status, stamp))
    conn.execute("UPDATE restaurant SET data_version=data_version+1")
    version = restaurant_record(conn)["data_version"]
    conn.execute("INSERT INTO coverage_events(date,channel_id,previous_status,status,source_data_version,created_at) VALUES (?,?,?,?,?,?)",
                 (body.date.isoformat(), body.channel_id, previous["status"] if previous else "unknown", body.status, version, stamp))
    conn.execute("UPDATE forecast_runs SET status='pending' WHERE status IN ('ready','insufficient_history')")
    return {"date": body.date, "channel_id": body.channel_id, "status": body.status, "updated_at": stamp}


def actual_metrics(summary):
    definitions = [("sales.units", "Observed units sold", summary["units"], "units"),
                   ("sales.orders", "Observed completed orders", str(summary["orders"]), "orders"),
                   ("sales.net_revenue", "Observed net item revenue", summary["net_revenue"], "USD"),
                   ("sales.average_order_revenue", "Average net item revenue per order", summary["average_order_revenue"], "USD")]
    return [{"id": key, "label": label, "value": value, "unit": unit, "kind": "actual", "period": summary["period"],
             "as_of": summary["as_of"], "coverage": summary["coverage"]["status"], "source_data_version": summary["source_data_version"],
             "evidence": summary["evidence"], "assumptions": summary["assumptions"]} for key, label, value, unit in definitions]
