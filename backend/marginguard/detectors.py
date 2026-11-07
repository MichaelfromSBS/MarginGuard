"""Measured demo policies. Findings and all numeric explanations are Python-owned."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json

from .analytics import ZERO, coverage_summary, dates, decimal_text, evidence, sales_rows
from .ingestion import identifier, insert, now
from .schemas import Alert

VERSION = "detectors_v2"


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


def detect_cost_increases(conn, as_of, forecast):
    changes = price_changes(conn, as_of)
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
        rising = [(i, old, new) for i, old, new in group if Decimal(new["unit_cost"]) > Decimal(old["unit_cost"])]
        if delta <= ZERO or not rising:
            continue
        raw_effects = [Decimal(ingredients[i].quantity) * (Decimal(new["unit_cost"]) - Decimal(old["unit_cost"])) for i, old, new in group]
        effects = [Decimal(decimal_text(value, money=True)) for value in raw_effects]
        # Keep displayed contributions equal to the displayed total change, even
        # with mixed increases/decreases and fractional-cent unit prices.
        effects[max(range(len(effects)), key=lambda index: abs(raw_effects[index]))] += delta - sum(effects, ZERO)
        items = [{"ingredient_id": i, "ingredient_name": new["name"], "quantity": ingredients[i].quantity, "base_unit": new["base_unit"],
                  "previous_price": old["unit_cost"], "current_price": new["unit_cost"],
                  "increase_pct": decimal_text((Decimal(new["unit_cost"]) / Decimal(old["unit_cost"]) - 1) * 100) if Decimal(old["unit_cost"]) else None,
                  "invoice_number": new["invoice_number"],
                  "price_effect": decimal_text(contribution, money=True)} for (i, old, new), contribution in zip(group, effects)]
        causes = "; ".join(f"{new['name']} increased from ${decimal_text(old['unit_cost'])} to ${decimal_text(new['unit_cost'])}/{new['base_unit']}" for _, old, new in rising)
        offsets = " Other ingredient changes in the same invoice are included in the net increase." if len(rising) != len(group) else ""
        record(conn, f"{VERSION}:cost:{document_id}", "projected_cost_increase", "Ingredient increases raise next-month cost",
               f"Projected ingredient cost for {forecast.horizon.start}–{forecast.horizon.end} increased from ${decimal_text(previous_cost, money=True)} to ${decimal_text(next_cost, money=True)} (+${decimal_text(delta, money=True)}) because {causes}.{offsets} Expected sales volume is held fixed; this is a projected ingredient cost, not total operating expense.",
               {"previous_cost": decimal_text(previous_cost, money=True), "current_cost": decimal_text(next_cost, money=True),
                "policy": "positive_ingredient_change_and_positive_total_cost_change",
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
        if day != end:
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
        revenue = sum((Decimal(r["net_amount"]) for r in rows[day.isoformat()]), ZERO)
        orders = len({r["receipt_id"] for r in rows[day.isoformat()]})
        display_drop = decimal_text(drop.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        record(conn, event_key, "unusual_sales", f"Unusual sales on {day}",
               f"Report issued {as_of} for the previous day, {day}: {orders} orders, {decimal_text(actual)} units and ${decimal_text(revenue, money=True)} net sales. Units were {display_drop}% below the previous four complete {day.strftime('%A')}s' mean of {decimal_text(mean)} units. The cause is not established; tax and tips are excluded from net sales.",
               {"date": day.isoformat(), "reported_on": as_of.isoformat(), "orders": orders,
                "net_revenue": decimal_text(revenue, money=True), "units": decimal_text(actual), "baseline_units": decimal_text(mean),
                "threshold_pct": str(settings.sales_drop_pct), "minimum_drop_units": str(settings.sales_drop_min_units),
                "drop_pct": decimal_text(drop), "baseline_dates": [d.isoformat() for d in previous],
                "coverage": "complete_in_all_channels", "evidence_is_sample": True}, refs,
               "Check opening hours, promotions, local events and receipt-import completeness before attributing a cause.", update=True)
    for row in conn.execute("""SELECT id,event_key FROM alerts WHERE type='unusual_sales' AND status!='resolved'
        AND json_extract(finding_json,'$.date')=?""", (end.isoformat(),)).fetchall():
        if row["event_key"] not in active_events:
            conn.execute("UPDATE alerts SET status='resolved',updated_at=? WHERE id=?", (now(), row["id"]))


def run_detectors(conn, settings, as_of, forecast):
    detect_cost_increases(conn, as_of, forecast)
    detect_sales(conn, settings, as_of)
