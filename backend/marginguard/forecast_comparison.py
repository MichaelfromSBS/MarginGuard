"""Read-only attribution between immutable, originally-ready forecast snapshots.

Ingredient demand changes include projected volume and dish mix. The module
never reconstructs a past forecast from today's recipes or supplier prices.
"""
import json
from decimal import Decimal, DecimalException, localcontext

from pydantic import ValidationError

from .analytics import ZERO, decimal_text
from .errors import DomainError
from .schemas import ForecastResponse

MAX_SNAPSHOT_CHARACTERS = 2_000_000
MAX_INGREDIENTS = 200


def _unavailable():
    return DomainError("forecast_comparison_unavailable", "The selected saved forecast does not contain a valid, originally-ready ingredient-cost snapshot.", 409)


def _incompatible(reason):
    return DomainError("forecast_comparison_incompatible", "These forecast snapshots cannot be attributed on the same basis. " + reason, 409)


def _load(conn, run_id):
    row = conn.execute("""SELECT r.*,s.response_json FROM forecast_runs r
        LEFT JOIN forecast_snapshots s ON s.run_id=r.id WHERE r.id=?""", (run_id,)).fetchone()
    if row is None:
        raise DomainError("forecast_not_found", "A selected forecast does not exist.", 404)
    if not row["response_json"] or len(row["response_json"]) > MAX_SNAPSHOT_CHARACTERS:
        raise _unavailable()
    try:
        snapshot = ForecastResponse.model_validate_json(row["response_json"])
        policy = json.loads(row["assumptions_json"])
    except (ValidationError, ValueError, TypeError):
        raise _unavailable() from None
    if not isinstance(policy, dict) or snapshot.status != "ready":
        raise _unavailable()
    if (snapshot.id != row["id"] or snapshot.method != row["method"]
            or snapshot.horizon.start.isoformat() != row["horizon_start"]
            or snapshot.horizon.end.isoformat() != row["horizon_end"]
            or snapshot.source_data_version != row["source_data_version"]):
        raise _unavailable()
    metrics = [m for m in snapshot.metrics if m.id == "forecast.ingredient_cost"]
    if len(metrics) != 1:
        raise _unavailable()
    cost = metrics[0]
    if (cost.value is None or cost.unit != "USD" or cost.kind != "projected"
            or cost.period != snapshot.horizon or cost.source_data_version != snapshot.source_data_version
            or Decimal(cost.value) < 0 or not snapshot.ingredients or len(snapshot.ingredients) > MAX_INGREDIENTS):
        raise _unavailable()
    ingredients = {i.ingredient_id: i for i in snapshot.ingredients}
    if len(ingredients) != len(snapshot.ingredients):
        raise _unavailable()
    headline = Decimal(cost.value)
    raw_cost = sum((Decimal(i.quantity) * Decimal(i.unit_cost) for i in snapshot.ingredients), ZERO)
    if (sum((Decimal(i.cost) for i in snapshot.ingredients), ZERO) != headline
            or Decimal(decimal_text(raw_cost, money=True)) != headline):
        raise _unavailable()
    series = {(s.dish_id, s.channel_id): s for s in snapshot.series}
    if (not series or len(series) != len(snapshot.series)
            or any(s.status != "ready" or not s.recipe_version_id for s in snapshot.series)):
        raise _unavailable()
    return snapshot, ingredients, series, headline, policy, row["status"]


def _compare(conn, previous_id, current_id):
    previous, old, old_series, previous_cost, old_policy, previous_status = _load(conn, previous_id)
    current, new, new_series, current_cost, new_policy, current_status = _load(conn, current_id)
    if previous.horizon != current.horizon:
        raise _incompatible("Choose the same forecast month.")
    if previous.method != current.method:
        raise _incompatible("The forecast methods differ.")
    if any(old_policy.get(key) != new_policy.get(key) for key in ("history_weeks", "min_observations")):
        raise _incompatible("The forecast training policies differ.")
    if set(old_series) != set(new_series) or any(old_series[key].recipe_version_id != new_series[key].recipe_version_id for key in old_series):
        raise _incompatible("The dish/channel series or recipe versions changed.")
    if set(old) != set(new):
        raise _incompatible("The ingredient sets changed.")
    if any(old[key].base_unit != new[key].base_unit for key in old):
        raise _incompatible("Ingredient base units changed.")

    evidence = [{"kind": "forecast_run", "record_id": previous.id}, {"kind": "forecast_run", "record_id": current.id}]
    effects = []
    for ingredient_id in sorted(old):
        before, after = old[ingredient_id], new[ingredient_id]
        q0, q1 = Decimal(before.quantity), Decimal(after.quantity)
        p0, p1 = Decimal(before.unit_cost), Decimal(after.unit_cost)
        usage = Decimal(decimal_text((q1 - q0) * p0, money=True))
        price = Decimal(decimal_text(q0 * (p1 - p0), money=True))
        joint = Decimal(decimal_text((q1 - q0) * (p1 - p0), money=True))
        change = Decimal(after.cost) - Decimal(before.cost)
        effects.append({"ingredient_id": ingredient_id, "base_unit": before.base_unit,
            "previous_quantity": before.quantity, "current_quantity": after.quantity,
            "previous_price": before.unit_cost, "current_price": after.unit_cost,
            "previous_cost": before.cost, "current_cost": after.cost,
            "change": decimal_text(change, money=True), "usage_effect": decimal_text(usage, money=True),
            "price_effect": decimal_text(price, money=True), "interaction_effect": decimal_text(joint, money=True),
            "rounding_residual": decimal_text(change - usage - price - joint, money=True)})
        if q0 != q1 or p0 != p1 or change:
            evidence.extend(i.evidence.model_dump(mode="json") for i in (before, after) if i.evidence.kind == "invoice_line")

    usage = sum((Decimal(i["usage_effect"]) for i in effects), ZERO)
    price = sum((Decimal(i["price_effect"]) for i in effects), ZERO)
    joint = sum((Decimal(i["interaction_effect"]) for i in effects), ZERO)
    change = current_cost - previous_cost
    limitations = [
        "This compares saved ingredient-consumption projections, not actual COGS, total operating expense or profit.",
        "The usage effect includes projected sales volume, dish mix and training-window changes; it is not a proven cause of real sales changes.",
        "Price effect uses previous quantities, usage effect uses previous prices, and interaction captures both changing together.",
        "Effects round half up to cents; the explicit residual reconciles them to saved displayed costs and ingredient allocations.",
    ]
    if previous_status != "ready":
        limitations.append("The previous run is no longer marked current; its originally-ready immutable values are retained for historical comparison.")
    if current_status != "ready":
        limitations.append("The selected current run is no longer marked current; this is a historical comparison, not a current planning forecast.")
    owner = conn.execute("SELECT data_version FROM restaurant ORDER BY id LIMIT 1").fetchone()
    if owner and current.source_data_version != owner["data_version"]:
        limitations.append("The selected current snapshot uses an older ledger version; the comparison does not refresh or recompute it.")
    unique = []
    seen = set()
    for reference in evidence:
        key = json.dumps(reference, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return {"previous_id": previous.id, "current_id": current.id,
        "horizon": current.horizon.model_dump(mode="json"),
        "previous_cost": decimal_text(previous_cost, money=True), "current_cost": decimal_text(current_cost, money=True),
        "change": decimal_text(change, money=True), "usage_effect": decimal_text(usage, money=True),
        "price_effect": decimal_text(price, money=True), "interaction_effect": decimal_text(joint, money=True),
        "rounding_residual": decimal_text(change - usage - price - joint, money=True),
        "ingredient_effects": effects, "limitations": limitations, "evidence": unique,
        "source_data_version": current.source_data_version}


def compare_forecasts(conn, previous_id: str, current_id: str) -> dict:
    """Caller owns a read-only snapshot transaction; this function executes SELECTs only."""
    try:
        with localcontext() as context:
            context.prec = 100
            return _compare(conn, previous_id, current_id)
    except DecimalException:
        raise _unavailable() from None
