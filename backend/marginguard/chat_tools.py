"""Whitelisted, read-only owner questions. All prose/numeric facts come from code."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from . import analytics, forecasting
from .analytics import ZERO, decimal_text, evidence
from .detectors import alert_payload
from .errors import DomainError
from .ingestion import now, restaurant_record
from .schemas import Identifier, Metric, Period


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatedArgs(Args):
    as_of: date | None = None

    @field_validator("as_of", mode="before")
    @classmethod
    def iso_date(cls, value):
        if value is not None and not isinstance(value, (str, date)):
            raise ValueError("Dates must be ISO date strings.")
        return value


class SalesArgs(DatedArgs):
    period: Literal["last_7_days", "last_7_complete_days", "last_week", "this_week", "yesterday", "this_month", "last_month", "custom"] = "last_7_days"
    start: date | None = None
    end: date | None = None
    dish_id: Identifier | None = None
    channel_id: Literal["in_store", "delivery"] | None = None
    breakdown: Literal["none", "dish", "channel", "day"] = "none"
    rank_by: Literal["units", "net_revenue"] = "units"

    @field_validator("start", "end", mode="before")
    @classmethod
    def iso_dates(cls, value):
        return cls.iso_date(value)

    @model_validator(mode="after")
    def period_shape(self):
        if self.period == "custom" and (self.start is None or self.end is None):
            raise ValueError("Custom periods require both start and end.")
        if self.period != "custom" and (self.start is not None or self.end is not None):
            raise ValueError("Explicit dates require period=custom.")
        return self


class IngredientArgs(DatedArgs):
    ingredient_id: Identifier
    start: date | None = None
    end: date | None = None

    @field_validator("start", "end", mode="before")
    @classmethod
    def iso_dates(cls, value):
        return cls.iso_date(value)


class DishArgs(DatedArgs):
    dish_id: Identifier | None = None
    channel_id: Literal["in_store", "delivery"] | None = None


class ForecastArgs(Args):
    month: str | None = None
    dish_id: Identifier | None = None
    channel_id: Literal["in_store", "delivery"] | None = None

    @field_validator("month")
    @classmethod
    def calendar_month(cls, value):
        if value is not None:
            import re
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value) or not 1900 <= int(value[:4]) <= 9998:
                raise ValueError("Month must be YYYY-MM.")
        return value


class AlertArgs(Args):
    status: Literal["new", "acknowledged", "resolved", "all"] = "new"
    type: Literal["projected_cost_increase", "unusual_sales"] | None = None
    month: str | None = None

    @field_validator("month")
    @classmethod
    def calendar_month(cls, value):
        return ForecastArgs.calendar_month(value)


class CompareArgs(Args):
    previous_id: Identifier | None = None
    current_id: Identifier | None = None

    @model_validator(mode="after")
    def both_ids(self):
        if (self.previous_id is None) != (self.current_id is None):
            raise ValueError("Specify both snapshot IDs or omit both.")
        return self


TOOL_ARGUMENTS = {"get_sales_summary": SalesArgs, "get_ingredient_history": IngredientArgs,
    "get_dish_cost": DishArgs, "get_month_forecast": ForecastArgs,
    "get_alerts": AlertArgs, "explain_forecast_change": CompareArgs}
TOOL_DESCRIPTIONS = {
    "get_sales_summary": "Observed approved net sales, units, orders and optional dish/channel/day rankings. last_week is the previous Monday-Sunday calendar week; last_7_days is the seven finished dates. last_7_complete_days explicitly selects seven fully covered past dates and reports which dates.",
    "get_ingredient_history": "Approved supplier unit-price history and change for a known ingredient. Default window is the last eight weeks including the as-of date.",
    "get_dish_cost": "Modeled replacement ingredient cost per dish, with recipe/invoice evidence; optional channel contribution assumptions. Omit dish_id only when all configured dishes are requested.",
    "get_month_forecast": "Read an existing saved forecast for next calendar month (default) or month YYYY-MM. Never calculate or write a forecast. Optional dish/channel filtering.",
    "get_alerts": "Read new alerts by default, or acknowledged/resolved/all. Optional month YYYY-MM selects projected-cost alerts by forecast horizon only; it cannot filter unusual-sales alerts. Does not acknowledge or resolve anything.",
    "explain_forecast_change": "Compare two saved ready calculation snapshots of the same horizon/recipe definition. Omit both IDs to choose the latest compatible pair. Separates ingredient usage/dish-mix, unit-price and interaction effects, not actual profit.",
}


@dataclass
class ToolResult:
    answer: str
    metrics: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unavailable: bool = False


def checked_as_of(value, today):
    value = value or today
    if value > today or not 1900 <= value.year <= 9998:
        raise DomainError("invalid_chat_date", "Observed data cannot use a future as-of date. Specify a past/current date or ask for a forecast.", 422)
    return value


def metric(conn, key, label, value, unit="USD", kind="actual", period=None, coverage="complete", refs=None, assumptions=None):
    return Metric(id=key, label=label, value=value, unit=unit, kind=kind, period=period, as_of=now(),
        coverage=coverage, source_data_version=restaurant_record(conn)["data_version"],
        evidence=(refs or [])[:4], assumptions=assumptions or [])


def money(value):
    return f"${Decimal(value):,.2f}"


def sales_period(conn, args, today):
    as_of = checked_as_of(args.as_of, today)
    end = as_of - timedelta(days=1)
    selected = None
    if args.period == "custom":
        start, end, _ = analytics.period_dates(restaurant_record(conn), args.start, args.end, as_of)
    elif args.period == "last_week":
        end = as_of - timedelta(days=as_of.weekday() + 1)
        start = end - timedelta(days=6)
    elif args.period == "this_week":
        start, end = as_of - timedelta(days=as_of.weekday()), as_of
    elif args.period == "yesterday":
        start = end
    elif args.period == "this_month":
        start, end = as_of.replace(day=1), as_of
    elif args.period == "last_month":
        end = as_of.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif args.period == "last_7_complete_days":
        start = as_of - timedelta(days=56)
        channels = [args.channel_id] if args.channel_id else [r[0] for r in conn.execute("SELECT id FROM channels ORDER BY id")]
        summary = analytics.coverage_summary(conn, start, end, channels)
        states = {(r["date"], r["channel_id"]): r["status"] for r in summary["days"]}
        selected = [d for d in analytics.dates(start, end) if channels and all(states[(d.isoformat(), c)] in {"complete", "closed"} for c in channels)][-7:]
        if len(selected) < 7:
            raise DomainError("insufficient_complete_days", "There are fewer than seven fully covered dates in the last eight weeks.", 409)
        start, end = selected[0], selected[-1]
    else:
        start = end - timedelta(days=6)
    return start, end, selected


def sales(conn, args, today):
    start, end, selected = sales_period(conn, args, today)
    summary = analytics.sales_summary(conn, start, end, dish_id=args.dish_id, channel_id=args.channel_id)
    if selected is not None and len(selected) != (end - start).days + 1:
        # Aggregate each confirmed date separately; missing dates inside the
        # span are never counted as complete or included in selected actuals.
        pieces = [analytics.sales_summary(conn, d, d, dish_id=args.dish_id, channel_id=args.channel_id) for d in selected]
        summary["units"] = decimal_text(sum((Decimal(p["units"]) for p in pieces), ZERO))
        summary["net_revenue"] = decimal_text(sum((Decimal(p["net_revenue"]) for p in pieces), ZERO), money=True)
        summary["orders"] = sum(p["orders"] for p in pieces)
        summary["average_order_revenue"] = decimal_text(Decimal(summary["net_revenue"]) / summary["orders"], money=True) if summary["orders"] else None
        summary["coverage"]["status"] = "complete"
        for dimension, key in [("by_day", "date"), ("by_dish", "dish_id"), ("by_channel", "channel_id")]:
            combined = {}
            for piece in pieces:
                for group in piece[dimension]:
                    target = combined.setdefault(group[key], {key: group[key], "units": ZERO, "net_revenue": ZERO, "orders": 0})
                    target["units"] += Decimal(group["units"])
                    target["net_revenue"] += Decimal(group["net_revenue"])
                    target["orders"] += group["orders"]
            summary[dimension] = [{**g, "units": decimal_text(g["units"]), "net_revenue": decimal_text(g["net_revenue"], money=True)} for g in combined.values()]
    raw = [r for r in analytics.sales_rows(conn, start, end) if (not selected or date.fromisoformat(r["local_date"]) in selected)
           and (not args.dish_id or r["dish_id"] == args.dish_id) and (not args.channel_id or r["channel_id"] == args.channel_id)]
    summary["evidence"] = [evidence(r) for r in raw[:8]]
    if selected:
        summary["assumptions"] = summary["assumptions"] + [
            "Totals include only these complete dates within the displayed period: " + ", ".join(d.isoformat() for d in selected) + "."]
    metrics = analytics.actual_metrics(summary)
    for item in metrics:
        item["evidence"] = item["evidence"][:4]
    limitations = [] if summary["coverage"]["status"] == "complete" else ["Receipt coverage is incomplete; these are observed totals, not full-period business sales."]
    text = f"From {start} through {end}, approved receipts show {summary['orders']} orders, {summary['units']} units and {money(summary['net_revenue'])} net item revenue. Tax and tips are excluded."
    if selected:
        text += " Selected complete dates: " + ", ".join(d.isoformat() for d in selected) + "."
    if args.dish_id or args.channel_id:
        text += " This is filtered to " + ", ".join(v for v in [args.dish_id, args.channel_id] if v) + "."
    if args.dish_id:
        text += " Orders count receipts containing the selected dish; their revenue includes only that dish."
    if args.breakdown != "none":
        dimension, field_name = {"dish": ("by_dish", "dish_id"), "channel": ("by_channel", "channel_id"), "day": ("by_day", "date")}[args.breakdown]
        groups = sorted(summary[dimension], key=lambda g: (-Decimal(g[args.rank_by]), str(g[field_name])))[:10]
        names = {r["id"]: r["name"] for r in conn.execute("SELECT id,name FROM dishes")} if args.breakdown == "dish" else {}
        lines = []
        for group in groups:
            key = group[field_name]
            name = names.get(key, str(key).replace("_", " "))
            refs = [evidence(r) for r in raw if str(r[{"dish": "dish_id", "channel": "channel_id", "day": "local_date"}[args.breakdown]]) == str(key)][:3]
            for field_name2, label, unit in [("units", "units sold", "units"), ("net_revenue", "net sales", "USD")]:
                metrics.append(metric(conn, f"sales.{args.breakdown}.{key}.{field_name2}", f"{name} {label}", group[field_name2], unit,
                    period=summary["period"], coverage=summary["coverage"]["status"], refs=refs, assumptions=analytics.SALES_ASSUMPTIONS))
            lines.append(f"{name}: {group['units']} units, {money(group['net_revenue'])} net sales")
        text += "\n" + "\n".join(lines)
    return ToolResult(text, metrics, summary["evidence"], limitations)


def ingredient_history(conn, args, today):
    as_of = checked_as_of(args.as_of, today)
    start, end, _ = analytics.period_dates(restaurant_record(conn), args.start or as_of - timedelta(days=55), args.end or as_of, as_of)
    ingredient = conn.execute("SELECT * FROM ingredients WHERE id=?", (args.ingredient_id,)).fetchone()
    if ingredient is None:
        raise DomainError("ingredient_not_found", "That ingredient is not in the configured catalog.", 404)
    query = """SELECT p.*,l.id AS line_id,l.source_text,l.source_page,v.document_id FROM ingredient_prices p
        JOIN invoice_lines l ON l.id=p.invoice_line_id JOIN invoices v ON v.id=l.invoice_id JOIN documents d ON d.id=v.document_id
        WHERE p.ingredient_id=? AND p.effective_date BETWEEN ? AND ? AND d.status='completed' AND v.currency='USD' AND p.base_unit=?"""
    values = (args.ingredient_id, start.isoformat(), end.isoformat(), ingredient["base_unit"])
    first = conn.execute(query + " ORDER BY p.effective_date,d.created_at,p.rowid LIMIT 1", values).fetchone()
    last = conn.execute(query + " ORDER BY p.effective_date DESC,d.created_at DESC,p.rowid DESC LIMIT 1", values).fetchone()
    if first is None:
        return ToolResult(f"No approved {ingredient['name']} prices were found from {start} through {end}.", unavailable=True)
    refs = [evidence({**dict(r), "id": r["line_id"]}, "invoice_line") for r in [first, last]]
    change = (Decimal(last["unit_cost"]) / Decimal(first["unit_cost"]) - 1) * 100 if Decimal(first["unit_cost"]) else None
    period = {"start": start, "end": end}
    metrics = [metric(conn, "ingredient.first_price", f"{ingredient['name']} first price per {ingredient['base_unit']}", first["unit_cost"], period=period, refs=refs[:1]),
               metric(conn, "ingredient.latest_price", f"{ingredient['name']} latest price per {ingredient['base_unit']}", last["unit_cost"], period=period, refs=refs[1:]),
               metric(conn, "ingredient.change_pct", f"{ingredient['name']} price change", decimal_text(change) if change is not None else None, "percent", period=period, refs=refs)]
    text = f"{ingredient['name']} changed from {money(first['unit_cost'])}/{ingredient['base_unit']} on {first['effective_date']} to {money(last['unit_cost'])}/{ingredient['base_unit']} on {last['effective_date']}."
    text += f" That is a {decimal_text(change)}% change over the requested window." if change is not None else " A percent change cannot be calculated from a zero starting price."
    return ToolResult(text, metrics, refs, ["Normalized approved invoice prices exclude unallocated freight and purchase tax."])


def dish_costs(conn, args, today):
    as_of = checked_as_of(args.as_of, today)
    ids = [args.dish_id] if args.dish_id else [r[0] for r in conn.execute("SELECT id FROM dishes ORDER BY id LIMIT 20")]
    metrics, refs, limitations, lines = [], [], [], []
    for dish_id in ids:
        result = analytics.dish_cost(conn, dish_id, as_of)
        evidence_refs = [i["evidence"] for i in result["ingredients"] if i["evidence"]]
        refs.extend(evidence_refs)
        limitations.extend(result["limitations"])
        metrics.append(metric(conn, f"dish.{dish_id}.ingredient_cost", f"{result['name']} ingredient cost", result["ingredient_cost"], kind="modeled", coverage="unknown" if result["limitations"] else "complete", refs=evidence_refs, assumptions=analytics.COST_ASSUMPTIONS))
        lines.append(f"As of {as_of}, {result['name']}'s replacement ingredient cost is {money(result['ingredient_cost'])} per dish." if result["ingredient_cost"] is not None else f"{result['name']} cannot be fully costed because a recipe input is missing.")
        if args.channel_id:
            channel = next((c for c in result["channels"] if c["channel_id"] == args.channel_id), None)
            if channel is None:
                raise DomainError("channel_not_found", "That channel is not in the configured catalog.", 404)
            metrics.append(metric(conn, f"dish.{dish_id}.contribution", f"{result['name']} {args.channel_id} modeled contribution", channel["contribution"], kind="modeled", coverage="unknown" if channel["contribution"] is None else "complete", refs=evidence_refs, assumptions=analytics.COST_ASSUMPTIONS))
            if channel["contribution"] is not None:
                lines.append(f"Modeled {args.channel_id} contribution is {money(channel['contribution'])}, using configured menu price, fees and packaging. This is not actual profit.")
    limitations.extend(analytics.COST_ASSUMPTIONS[:2])
    return ToolResult("\n".join(lines) or "No dishes are configured.", metrics, refs, limitations,
                      not any(m.value is not None for m in metrics))


def month_forecast(conn, args, today):
    start = date.fromisoformat(args.month + "-01") if args.month else forecasting.next_month(today)[0]
    row = conn.execute("""SELECT r.id FROM forecast_runs r JOIN forecast_snapshots s ON s.run_id=r.id
        WHERE r.horizon_start=? ORDER BY s.as_of_date DESC,r.created_at DESC,r.rowid DESC LIMIT 1""", (start.isoformat(),)).fetchone()
    if row is None:
        return ToolResult(f"No saved forecast exists for {start:%Y-%m}. Chat does not calculate forecasts; wait for automatic refresh or use Trends & Outlook.", unavailable=True)
    result = forecasting.get_forecast(conn, row["id"])
    refs = [{"kind": "forecast_run", "record_id": result.id}]
    if result.status != "ready" or result.as_of != today:
        reason = "out of date" if result.status == "pending" or result.as_of != today else result.status.replace("_", " ")
        return ToolResult(f"The saved {start:%Y-%m} forecast is {reason}; I cannot present its old totals as a current projection.", evidence=refs,
                          limitations=result.limitations + ["No recalculation was triggered by chat."], unavailable=True)
    metrics = [m.model_copy(deep=True) for m in result.metrics]
    by_id = {m.id: m for m in metrics}
    required = {"forecast.units": ("units", "units"), "forecast.revenue": ("revenue", "USD"),
                "forecast.ingredient_cost": ("ingredient_cost", "USD")}
    if len(by_id) != len(metrics) or any(key not in by_id or by_id[key].value is None or by_id[key].unit != unit
           or by_id[key].kind != "projected" or by_id[key].source_data_version != result.source_data_version
           or by_id[key].period != result.horizon for key, (_, unit) in required.items()):
        return ToolResult("The saved forecast has incomplete projection metrics and cannot be reported safely.",
                          evidence=refs, unavailable=True)
    if args.dish_id or args.channel_id:
        selected = [s for s in result.series if (not args.dish_id or s.dish_id == args.dish_id) and (not args.channel_id or s.channel_id == args.channel_id)]
        if not selected:
            raise DomainError("forecast_series_not_found", "That dish/channel is not represented in the saved forecast.", 404)
        if any(s.status != "ready" or any(getattr(s, key) is None for key, _ in required.values()) for s in selected):
            return ToolResult("The selected forecast series lacks sufficient history or required inputs.", evidence=refs,
                              limitations=result.limitations, unavailable=True)
        for metric_id, (key, _) in required.items():
            item = by_id[metric_id]
            item.value = decimal_text(sum((Decimal(getattr(s, key)) for s in selected), ZERO), money=item.unit == "USD")
            item.label = "Filtered " + item.label.lower()
    values = {m.id: m.value for m in metrics}
    text = f"For {result.horizon.start}–{result.horizon.end}, the saved forecast projects {Decimal(values['forecast.units']):,.2f} units, {money(values['forecast.revenue'])} net item revenue and {money(values['forecast.ingredient_cost'])} ingredient consumption cost."
    if args.dish_id or args.channel_id:
        text += " These are filtered totals for " + ", ".join(v for v in [args.dish_id, args.channel_id] if v) + "."
    return ToolResult(text, metrics, refs + [i.evidence.model_dump() for i in result.ingredients][:8], result.assumptions + result.limitations)


def alerts(conn, args, today):
    clauses, params = [], []
    if args.month and args.type == "unusual_sales":
        raise DomainError("invalid_chat_filter", "An alert month selects the projected-cost forecast horizon, not unusual-sales event dates.", 422)
    if args.status != "all":
        clauses.append("status=?")
        params.append(args.status)
    if args.type:
        clauses.append("type=?")
        params.append(args.type)
    if args.month:
        clauses.append("type='projected_cost_increase'")
        clauses.append("substr(json_extract(finding_json,'$.horizon.start'),1,7)=?")
        params.append(args.month)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = conn.execute("SELECT COUNT(*) FROM alerts" + where, params).fetchone()[0]
    rows = conn.execute("SELECT * FROM alerts" + where + " ORDER BY created_at DESC,id DESC LIMIT 10", params).fetchall()
    refs, lines = [], []
    for row in rows:
        record = alert_payload(row)
        lines.append(f"{record['title']}: {record['message']}")
        refs.extend(record["evidence"])
    count = metric(conn, "alerts.count", f"{args.status.title()} alerts", str(total), "units")
    scope = f" for the {args.month} projected-cost horizon" if args.month else ""
    return ToolResult(f"There are {total} matching {args.status} alerts{scope}." + ("\n" + "\n".join(lines) if lines else ""), [count], refs,
                      ["Showing the latest matching alerts only."] if total > 10 else [])


def forecast_change(conn, args, today):
    from .forecast_comparison import compare_forecasts
    previous_id, current_id = args.previous_id, args.current_id
    if current_id is None:
        current = forecasting.latest_forecast(conn, today)
        if current is None or current.status != "ready":
            return ToolResult("A current ready forecast is needed before comparing saved projections.", unavailable=True)
        current_row = conn.execute("SELECT rowid,created_at FROM forecast_runs WHERE id=?", (current.id,)).fetchone()
        candidates = conn.execute("""SELECT r.id FROM forecast_runs r JOIN forecast_snapshots s ON s.run_id=r.id
            WHERE r.horizon_start=? AND r.id!=? AND s.as_of_date<=?
            AND (r.created_at<? OR (r.created_at=? AND r.rowid<?))
            ORDER BY r.created_at DESC,r.rowid DESC LIMIT 20""",
            (current.horizon.start.isoformat(), current.id, today.isoformat(), current_row["created_at"],
             current_row["created_at"], current_row["rowid"])).fetchall()
        comparison = None
        for candidate in candidates:
            try:
                comparison = compare_forecasts(conn, candidate["id"], current.id)
                break
            except DomainError:
                continue
        if comparison is None:
            return ToolResult("There is no compatible earlier ready snapshot for a change comparison. Chat does not create one.", unavailable=True)
    else:
        comparison = compare_forecasts(conn, previous_id, current_id)
    refs = comparison["evidence"]
    names = [("previous_cost", "Previous projected ingredient cost"), ("current_cost", "Current projected ingredient cost"),
             ("change", "Projected cost change"), ("usage_effect", "Ingredient usage and dish-mix effect"),
             ("price_effect", "Supplier-price effect at previous usage"), ("interaction_effect", "Usage/price interaction"),
             ("rounding_residual", "Cent-rounding reconciliation")]
    metrics = [metric(conn, "forecast_change." + key, label, comparison[key], kind="projected", period=comparison["horizon"], refs=refs,
                      assumptions=comparison["limitations"]) for key, label in names]
    for item in metrics:
        item.source_data_version = comparison["source_data_version"]
    text = f"Between saved forecasts {comparison['previous_id']} and {comparison['current_id']}, ingredient consumption cost changed from {money(comparison['previous_cost'])} to {money(comparison['current_cost'])} ({money(comparison['change'])}). "
    text += f"Usage/dish-mix effect: {money(comparison['usage_effect'])}; supplier-price effect at old usage: {money(comparison['price_effect'])}; interaction: {money(comparison['interaction_effect'])}; rounding reconciliation: {money(comparison['rounding_residual'])}."
    changed = [row for row in comparison["ingredient_effects"] if Decimal(row["change"]) or Decimal(row["previous_price"]) != Decimal(row["current_price"])]
    names_by_id = {r["id"]: r["name"] for r in conn.execute("SELECT id,name FROM ingredients")}
    for row in sorted(changed, key=lambda r: -abs(Decimal(r["change"])))[:5]:
        text += f"\n{names_by_id.get(row['ingredient_id'], row['ingredient_id'])}: {money(row['previous_price'])} → {money(row['current_price'])}/{row['base_unit']}; projected consumption cost effect {money(row['change'])} (includes usage and price changes)."
    if len(changed) > 5:
        comparison["limitations"].append("Only the five largest ingredient changes are named; the aggregate attribution includes all ingredients.")
    return ToolResult(text, metrics, refs, comparison["limitations"])


HANDLERS = {"get_sales_summary": sales, "get_ingredient_history": ingredient_history, "get_dish_cost": dish_costs,
            "get_month_forecast": month_forecast, "get_alerts": alerts, "explain_forecast_change": forecast_change}


def execute_tool(conn, name, arguments, today):
    if name not in HANDLERS:
        raise DomainError("unknown_chat_tool", "That operation is not an available read-only tool.", 422)
    encoded = arguments if isinstance(arguments, str) else json.dumps(arguments)
    args = TOOL_ARGUMENTS[name].model_validate_json(encoded)
    return HANDLERS[name](conn, args, today), args.model_dump(mode="json")
