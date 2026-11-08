"""Read-only cost → proposed menu price → demand scenarios, never ledger writes."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, localcontext

from .analytics import ZERO, decimal_text, dish_cost
from .errors import DomainError
from .forecasting import get_forecast, rounded_allocations
from .schemas import PricingScenarioResponse


def scenario(conn, run_id, request):
    forecast = get_forecast(conn, run_id)
    if forecast.status != "ready" or forecast.as_of is None or forecast.training_period is None:
        raise DomainError("scenario_forecast_unavailable", "Calculate a current, ready forecast before exploring prices.", 409)
    reference_date = request.reference_date or forecast.as_of - timedelta(days=28)
    if reference_date > forecast.as_of or reference_date.year < 1900:
        raise DomainError("invalid_reference_date", "The cost reference date must be between 1900 and the forecast as-of date.", 422)
    overrides = {p.ingredient_id: Decimal(p.unit_cost) for p in request.ingredient_prices}
    menus = {(p.dish_id, p.channel_id): Decimal(p.price) for p in request.menu_prices}
    ingredient_ids = {i.ingredient_id for i in forecast.ingredients}
    series_ids = {(s.dish_id, s.channel_id) for s in forecast.series}
    if overrides.keys() - ingredient_ids or menus.keys() - series_ids:
        raise DomainError("scenario_unknown_input", "Choose ingredients and dish/channels present in this forecast.", 422)
    if any(p > 1000000 for p in overrides.values()):
        raise DomainError("scenario_price_out_of_range", "Ingredient prices must not exceed 1,000,000 per base unit.", 422)
    current = {s.dish_id: dish_cost(conn, s.dish_id, forecast.as_of) for s in forecast.series}
    reference = {key: dish_cost(conn, key, reference_date) for key in current}
    for key, cost in current.items():
        old = reference[key]
        if old["limitations"] or cost["limitations"] or old["recipe_version_id"] != cost["recipe_version_id"]:
            raise DomainError("scenario_reference_unavailable", "Choose a reference date with approved prices and the same recipe versions as the forecast.", 409)
    fraction = Decimal(request.cost_pass_through_pct) / 100
    elasticity = Decimal(request.price_elasticity)
    rows, revenues, costs = [], [], []
    quantities = defaultdict(lambda: ZERO)
    fixed_cost = ZERO
    for source in forecast.series:
        items = current[source.dish_id]["ingredients"]
        current_cost = sum((Decimal(i["quantity"]) * Decimal(i["unit_cost"]) for i in items), ZERO)
        reference_cost = sum((Decimal(i["quantity"]) * Decimal(i["unit_cost"]) for i in reference[source.dish_id]["ingredients"]), ZERO)
        new_cost = sum((Decimal(i["quantity"]) * overrides.get(i["ingredient_id"], Decimal(i["unit_cost"])) for i in items), ZERO)
        old_price = Decimal(source.menu_price)
        new_price = menus.get((source.dish_id, source.channel_id), old_price + fraction * (new_cost - reference_cost))
        new_price = Decimal(decimal_text(new_price, money=True))
        if old_price <= 0 or not old_price / 2 <= new_price <= old_price * 2:
            raise DomainError("scenario_price_out_of_range", "Scenario menu prices must be positive and within 50%–200% of current prices; larger changes are unsupported extrapolation.", 422)
        # Constant elasticity is an explicit owner assumption, not a fitted coefficient.
        with localcontext() as context:
            context.prec = 40
            multiplier = (new_price / old_price) ** elasticity
        units = Decimal(decimal_text(Decimal(source.units) * multiplier))
        revenues.append(units * new_price)
        costs.append(units * new_cost)
        fixed_cost += Decimal(source.units) * new_cost
        for item in items:
            quantities[item["ingredient_id"]] += units * Decimal(item["quantity"])
        rows.append({"dish_id": source.dish_id, "channel_id": source.channel_id,
            "reference_unit_cost": decimal_text(reference_cost), "current_unit_cost": decimal_text(current_cost),
            "scenario_unit_cost": decimal_text(new_cost), "current_menu_price": source.menu_price,
            "scenario_menu_price": decimal_text(new_price, money=True), "demand_multiplier": decimal_text(multiplier),
            "baseline_units": source.units, "units": decimal_text(units), "revenue": "0.00", "ingredient_cost": "0.00"})
    ingredients, ingredient_costs = [], []
    for source in forecast.ingredients:
        price = overrides.get(source.ingredient_id, Decimal(source.unit_cost))
        quantity = decimal_text(quantities[source.ingredient_id])
        ingredient_costs.append(Decimal(quantity) * price)
        ingredients.append({**source.model_dump(), "quantity": quantity, "unit_cost": decimal_text(price),
            "price_source": "owner_assumption" if source.ingredient_id in overrides else "approved_invoice"})
    total_cost = Decimal(decimal_text(sum(ingredient_costs, ZERO), money=True))
    revenue = Decimal(decimal_text(sum(revenues, ZERO), money=True))
    for row, cost, value in zip(rows, rounded_allocations(costs, total_cost), rounded_allocations(revenues, revenue)):
        row["ingredient_cost"], row["revenue"] = decimal_text(cost, money=True), decimal_text(value, money=True)
    for row, cost in zip(ingredients, rounded_allocations(ingredient_costs, total_cost)):
        row["cost"] = decimal_text(cost, money=True)
    history = defaultdict(list)
    for price in conn.execute("SELECT dish_id,channel_id,price,effective_date FROM menu_prices WHERE effective_date<=? ORDER BY effective_date,rowid", (forecast.as_of.isoformat(),)):
        history[(price["dish_id"], price["channel_id"])].append(price)
    varied = []
    for values in history.values():
        prior = [p for p in values if p["effective_date"] < forecast.training_period.start.isoformat()]
        relevant = prior[-1:] + [p for p in values if p["effective_date"] >= forecast.training_period.start.isoformat()]
        varied.append(len({Decimal(p["price"]) for p in relevant}) > 1)
    has_variation = any(varied)
    limitations = ["Price elasticity is an owner assumption, not learned from this restaurant or validated by the forecast backtest.",
        "This assumes independent dish demand: substitution, promotions, competitors, capacity, waste and inventory are not modeled.",
        "Revenue less ingredient cost excludes platform fees, packaging, labor, rent and other expenses; it is not profit."]
    if not has_variation:
        limitations.append("The recorded menu-price history has no usable within-series price variation for estimating price sensitivity.")
    return PricingScenarioResponse.model_validate({"forecast_id": forecast.id, "source_data_version": forecast.source_data_version,
        "horizon": forecast.horizon, "reference_date": reference_date, "price_elasticity": request.price_elasticity,
        "cost_pass_through_pct": request.cost_pass_through_pct, "units": decimal_text(sum((Decimal(r["units"]) for r in rows), ZERO)),
        "revenue": decimal_text(revenue, money=True), "ingredient_cost": decimal_text(total_cost, money=True),
        "revenue_less_ingredient_cost": decimal_text(revenue - total_cost, money=True),
        "fixed_demand_ingredient_cost": decimal_text(fixed_cost, money=True), "series": rows, "ingredients": ingredients,
        "assumptions": [
            "What-if scenario only; no menu prices, sales, forecasts or alerts are changed.",
            "Proposed price = current menu price + pass-through fraction × (scenario recipe cost − reference-date recipe cost), rounded to cents. An explicit menu override takes precedence.",
            "100% pass-through transfers the ingredient cost change in dollars, not the same percentage increase as ingredients. Zero pass-through holds menu prices unless explicitly overridden.",
            "Scenario units = base forecast units × (proposed price / current menu price) ^ assumed elasticity. Current prices are the baseline demand anchor.",
            "A negative elasticity reduces demand as menu price rises, and increases demand as it falls. Supplier costs alone never imply a selling-price change.",
            "Current recipe quantities are fixed. The reference date defaults to 28 days before the forecast as-of date.",
            "Ingredient evidence traces approved source prices; a price marked owner_assumption is hypothetical and is not substantiated by that invoice."
        ], "limitations": limitations})
