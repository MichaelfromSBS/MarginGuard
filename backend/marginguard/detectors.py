"""Measured demo policies. Findings and all numeric explanations are Python-owned."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
import hashlib
import json

from .analytics import ZERO, coverage_summary, dates, decimal_text, evidence, sales_rows
from .ingestion import identifier, insert, now
from .schemas import Alert

VERSION = "detectors_v1"


def alert_payload(row):
    row = dict(row)
    row["evidence"] = json.loads(row["evidence_json"])
    row["finding"] = json.loads(row["finding_json"])
    return {field: row[field] for field in Alert.model_fields}


def record(conn, event_key, kind, title, message, finding, references, suggestion, *, update=False):
    encoded = json.dumps({"finding": finding, "evidence": references}, sort_keys=True)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    old = conn.execute("SELECT * FROM alerts WHERE event_key=?", (event_key,)).fetchone()
    if old and (old["fingerprint"] == fingerprint or not update):
        return old["id"]
    stamp = now()
    if old:
        alert_id, revision = old["id"], old["revision"] + 1
        conn.execute("""UPDATE alerts SET title=?,message=?,finding_json=?,evidence_json=?,fingerprint=?,revision=?,
            suggestion=?,explanation_status='pending',status='new',updated_at=? WHERE id=?""",
            (title, message, json.dumps(finding), json.dumps(references), fingerprint, revision, suggestion, stamp, alert_id))
    else:
        alert_id, revision = identifier("alert"), 1
        insert(conn, "alerts", id=alert_id, event_key=event_key, type=kind, severity="warning", status="new", title=title,
               message=message, finding_json=json.dumps(finding), evidence_json=json.dumps(references), fingerprint=fingerprint,
               revision=revision, suggestion=suggestion, explanation_status="pending", calculation_version=VERSION, created_at=stamp, updated_at=stamp)
    return alert_id


def price_changes(conn, as_of):
    rows = conn.execute("""SELECT p.*,i.name,l.id AS line_id,l.source_text,l.source_page,l.quantity,l.purchase_unit,
        l.pack_size,l.pack_unit,l.unit_price,l.line_total,v.document_id,v.invoice_number
        FROM ingredient_prices p JOIN ingredients i ON i.id=p.ingredient_id
        JOIN invoice_lines l ON l.id=p.invoice_line_id JOIN invoices v ON v.id=l.invoice_id
        JOIN documents d ON d.id=v.document_id WHERE p.effective_date<=? AND d.status='completed'
        AND p.base_unit=i.base_unit AND v.currency='USD'
        ORDER BY p.ingredient_id,p.effective_date,d.created_at,p.rowid""", (as_of.isoformat(),)).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["ingredient_id"]].append(dict(row))
    changes = []
    for ingredient, values in grouped.items():
        current = Decimal(values[-1]["unit_cost"])
        index = len(values) - 1
        while index >= 0 and Decimal(values[index]["unit_cost"]) == current:
            index -= 1
        if index < 0:
            continue
        # Retain the invoice that first changed the price. Repacked/same-price
        # invoices do not become a second event or another notification.
        old, new = values[index], values[index + 1]
        changes.append((ingredient, old, new))
    return changes


def price_reference(row):
    return evidence({**row, "id": row["line_id"]}, "invoice_line")


def detect_prices(conn, settings, as_of, forecast):
    changes = price_changes(conn, as_of)
    for ingredient, old, new in changes:
        before, after = Decimal(old["unit_cost"]), Decimal(new["unit_cost"])
        if before <= 0 or after <= before:
            continue
        percent = (after / before - 1) * 100
        if percent <= Decimal(str(settings.price_spike_pct)):
            continue
        finding = {"ingredient_id": ingredient, "base_unit": new["base_unit"], "previous_price": old["unit_cost"],
                   "threshold_pct": str(settings.price_spike_pct),
                   "current_price": new["unit_cost"], "increase_pct": decimal_text(percent),
                   "previous_date": old["effective_date"], "effective_date": new["effective_date"],
                   "invoice_number": new["invoice_number"], "purchase": {k: new[k] for k in ["quantity", "purchase_unit", "pack_size", "pack_unit", "unit_price", "line_total"]}}
        record(conn, f"{VERSION}:price:{ingredient}:{new['id']}", "ingredient_price_spike", f"{new['name']} price increased",
               f"{new['name']} rose from ${decimal_text(before, money=True)} to ${decimal_text(after, money=True)}/{new['base_unit']} ({decimal_text(percent)}%) on {new['effective_date']}. Invoice {new['invoice_number']} supplies the new price.",
               finding, [price_reference(old), price_reference(new)], "Compare the supplier quote and invoice, and review the affected dish's ingredient cost.")
    if forecast is None or forecast.status != "ready":
        return
    ingredients = {i.ingredient_id: i for i in forecast.ingredients}
    groups = defaultdict(list)
    for ingredient, old, new in changes:
        if ingredient in ingredients:
            groups[new["document_id"]].append((ingredient, old, new))
    current_cost = sum((Decimal(i.quantity) * Decimal(i.unit_cost) for i in forecast.ingredients), ZERO)
    for document_id, group in groups.items():
        effect = sum((Decimal(ingredients[i].quantity) * (Decimal(new["unit_cost"]) - Decimal(old["unit_cost"])) for i, old, new in group), ZERO)
        previous_cost = Decimal(decimal_text(current_cost - effect, money=True))
        next_cost = Decimal(decimal_text(current_cost, money=True))
        delta = next_cost - previous_cost
        if delta <= Decimal(str(settings.projected_cost_increase_usd)):
            continue
        items = [{"ingredient_id": i, "quantity": ingredients[i].quantity, "base_unit": new["base_unit"],
                  "previous_price": old["unit_cost"], "current_price": new["unit_cost"],
                  "price_effect": decimal_text(Decimal(ingredients[i].quantity) * (Decimal(new["unit_cost"]) - Decimal(old["unit_cost"])), money=True)} for i, old, new in group]
        record(conn, f"{VERSION}:cost:{document_id}:{forecast.horizon.start}", "projected_cost_increase", "Supplier change raises projected ingredient cost",
               f"Holding demand fixed for {forecast.horizon.start}–{forecast.horizon.end}, this supplier-price change raises ingredient consumption cost by ${decimal_text(delta, money=True)} (${decimal_text(previous_cost, money=True)} → ${decimal_text(next_cost, money=True)}). This is a planning estimate, not a realized loss.",
               {"previous_cost": decimal_text(previous_cost, money=True), "current_cost": decimal_text(next_cost, money=True),
                "threshold_usd": str(settings.projected_cost_increase_usd),
                "increase": decimal_text(delta, money=True), "fixed_demand_forecast_id": forecast.id,
                "horizon": forecast.horizon.model_dump(mode="json"), "changes": items},
               [{"kind": "forecast_run", "record_id": forecast.id}] + [ref for _, old, new in group for ref in [price_reference(old), price_reference(new)]],
               "Review affected dishes, supplier alternatives and menu pricing; demand and inventory effects are not included.")


def detect_sales(conn, settings, as_of):
    start, end = as_of - timedelta(weeks=8), as_of - timedelta(days=1)
    coverage = coverage_summary(conn, start, end)
    channels = [r[0] for r in conn.execute("SELECT id FROM channels ORDER BY id")]
    states = {(r["date"], r["channel_id"]): r["status"] for r in coverage["days"]}
    complete_days = [d for d in dates(start, end) if channels and all(states[(d.isoformat(), c)] == "complete" for c in channels)]
    totals, rows = defaultdict(lambda: ZERO), defaultdict(list)
    for row in sales_rows(conn, start, end):
        totals[row["local_date"]] += Decimal(row["quantity"])
        rows[row["local_date"]].append(row)
    active_events = set()
    for day in complete_days:
        if day < as_of - timedelta(days=settings.sales_alert_recent_days):
            continue
        previous = [d for d in complete_days if d < day and d.weekday() == day.weekday()][-4:]
        if len(previous) < 4:
            continue
        mean = sum((totals[d.isoformat()] for d in previous), ZERO) / 4
        actual = totals[day.isoformat()]
        if mean <= 0 or mean - actual < Decimal(str(settings.sales_drop_min_units)):
            continue
        drop = (1 - actual / mean) * 100
        if drop <= Decimal(str(settings.sales_drop_pct)):
            continue
        refs = [evidence(r) for r in rows[day.isoformat()][:4]]
        for prior in previous:
            refs.extend(evidence(r) for r in rows[prior.isoformat()][:3])
        event_key = f"{VERSION}:sales:{day}"
        active_events.add(event_key)
        record(conn, event_key, "unusual_sales", f"Unusual sales on {day}",
               f"Complete-day sales were {decimal_text(actual)} units on {day}, {decimal_text(drop)}% below the previous four complete {day.strftime('%A')}s' mean of {decimal_text(mean)} units. The reason is not established.",
               {"date": day.isoformat(), "units": decimal_text(actual), "baseline_units": decimal_text(mean),
                "threshold_pct": str(settings.sales_drop_pct), "minimum_drop_units": str(settings.sales_drop_min_units),
                "drop_pct": decimal_text(drop), "baseline_dates": [d.isoformat() for d in previous],
                "coverage": "complete_in_all_channels", "evidence_is_sample": True}, refs,
               "Check opening hours, promotions, local events and receipt-import completeness before attributing a cause.", update=True)
    for row in conn.execute("""SELECT id,event_key FROM alerts WHERE type='unusual_sales' AND status!='resolved'
        AND json_extract(finding_json,'$.date') BETWEEN ? AND ?""", ((as_of - timedelta(days=settings.sales_alert_recent_days)).isoformat(), end.isoformat())).fetchall():
        if row["event_key"] not in active_events:
            conn.execute("UPDATE alerts SET status='resolved',updated_at=? WHERE id=?", (now(), row["id"]))


def detect_quality(conn):
    rows = conn.execute("SELECT * FROM documents WHERE status IN ('needs_review','failed') ORDER BY id").fetchall()
    for row in rows:
        issues = json.loads(row["validation_issues_json"])
        record(conn, f"{VERSION}:quality:{row['id']}", "data_quality", f"Document needs attention: {row['filename']}",
               "This document is excluded from approved financial totals. " + (row["error_message"] or "Review its source and validation notes."),
               {"document_id": row["id"], "filename": row["filename"], "error_code": row["error_code"], "issues": issues, "classification": "data_quality_not_proven_loss"},
               [{"kind": "document", "record_id": row["id"], "document_id": row["id"]}],
               "Inspect the original document, correct the mapping or amounts, or retry after fixing configuration.", update=True)
    # A corrected/approved document resolves its data-quality finding. The old
    # finding remains in the audit history and cannot send a late pending alert.
    conn.execute("""UPDATE alerts SET status='resolved',updated_at=? WHERE type='data_quality' AND status!='resolved'
        AND event_key IN (SELECT ? || id FROM documents WHERE status='completed')""", (now(), f"{VERSION}:quality:"))


def run_detectors(conn, settings, as_of, forecast):
    detect_prices(conn, settings, as_of, forecast)
    detect_sales(conn, settings, as_of)
    detect_quality(conn)
