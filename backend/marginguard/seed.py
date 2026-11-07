"""Explicit synthetic checkpoint-one data. Not an invoice extraction pipeline."""

from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .db import MigrationError, connect, initialize_database

SEED_NAME = "checkpoint_1_demo_v1"
RESTAURANT_ID = "tartan_burger_co"
STAMP = "2026-11-07T19:00:00+00:00"
BUSINESS_TABLES = (
    "restaurant", "ingredients", "dishes", "channels", "menu_prices",
    "recipe_versions", "recipe_items", "documents", "processing_jobs",
    "invoices", "invoice_lines", "ingredient_prices", "receipts",
    "receipt_items", "daily_coverage", "forecast_runs", "forecast_values",
    "alerts", "notification_outbox", "vendors", "restaurant_calendar",
    "document_pages", "review_events", "data_changes", "import_batches",
)


def _insert(connection, table: str, **values):
    # All identifiers originate in this module, never in a request.
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))


def _counts(connection) -> dict[str, int]:
    return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in BUSINESS_TABLES}


def _document(connection, identifier: str, kind: str, source: str):
    _insert(connection, "documents", id=identifier, type=kind,
            filename=f"synthetic_{identifier}.txt", sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            media_type="text/plain", source_text=source, status="completed", created_at=STAMP, updated_at=STAMP, is_demo=1)


def _invoice_line_text(line: tuple) -> str:
    _, description, quantity, purchase_unit, _, _, unit_price, line_total, _, _ = line
    return f"{description} | quantity {quantity} {purchase_unit} | unit price ${unit_price} | line total ${line_total}"


def seed_demo(path: str | Path) -> dict:
    """Seed an empty database once. Never merge fixtures into existing business data."""
    initialize_database(path)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        marker = connection.execute("SELECT name FROM seed_runs WHERE name = ?", (SEED_NAME,)).fetchone()
        if marker:
            restaurant = connection.execute("SELECT is_demo FROM restaurant WHERE id = ?", (RESTAURANT_ID,)).fetchone()
            if not restaurant or restaurant["is_demo"] != 1:
                raise ValueError("Demo seed marker exists without its demo restaurant; review the database manually.")
            return {"seeded": False, "restaurant_id": RESTAURANT_ID, "counts": _counts(connection)}
        if any(_counts(connection).values()):
            raise ValueError("Refusing to seed demo data into a database that already contains business records.")

        _insert(connection, "restaurant", id=RESTAURANT_ID, name="Tartan Burger Co.", currency="USD",
                timezone="America/New_York", data_version=1, is_demo=1)
        _insert(connection, "vendors", id="ridgeline_foodservice", name="Ridgeline Foodservice (fictional)", aliases_json='["Ridgeline Foodservice"]')
        ingredients = [
            ("beef", "Ground beef 80/20", "lb", ["ground chuck", "ground beef"]),
            ("bun", "Burger bun", "each", ["brioche bun"]),
            ("produce", "Burger produce portion", "each", ["lettuce tomato portion"]),
            ("cheese", "Cheese slice", "each", ["american cheese"]),
            ("veggie_patty", "Veggie patty", "each", ["plant patty"]),
        ]
        for identifier, name, unit, aliases in ingredients:
            _insert(connection, "ingredients", id=identifier, name=name, base_unit=unit, aliases_json=json.dumps(aliases))
        for identifier, name, rate, packaging in [
            ("in_store", "In-store", "0.00", "0.00"),
            ("delivery", "Delivery (fictional fee assumption)", "0.30", "0.60"),
        ]:
            _insert(connection, "channels", id=identifier, name=name, fee_rate=rate, packaging_cost=packaging)
        recipes = {
            "classic_burger": ("Classic Burger", "12.00", [("beef", "0.50", "lb"), ("bun", "1", "each"), ("produce", "1", "each")]),
            "cheeseburger": ("Cheeseburger", "13.00", [("beef", "0.50", "lb"), ("bun", "1", "each"), ("produce", "1", "each"), ("cheese", "1", "each")]),
            "veggie_burger": ("Veggie Burger", "11.00", [("veggie_patty", "1", "each"), ("bun", "1", "each"), ("produce", "1", "each")]),
        }
        for identifier, (name, price, items) in recipes.items():
            _insert(connection, "dishes", id=identifier, name=name)
            for channel in ("in_store", "delivery"):
                _insert(connection, "menu_prices", id=f"menu_{identifier}_{channel}_v1", dish_id=identifier,
                        channel_id=channel, price=price, effective_date="2026-11-01")
            recipe_id = f"recipe_{identifier}_v1"
            _insert(connection, "recipe_versions", id=recipe_id, dish_id=identifier, effective_date="2026-11-01")
            for ingredient, quantity, unit in items:
                _insert(connection, "recipe_items", id=f"{recipe_id}_{ingredient}", recipe_version_id=recipe_id,
                        ingredient_id=ingredient, quantity=quantity, unit=unit)

        baseline_lines = [
            ("beef", "GROUND CHUCK 80/20 - 2 CASES, 10 LB EACH", "2", "case", "10", "lb", "40.00", "80.00", "4.00", "lb"),
            ("bun", "Burger buns - 100 each", "100", "each", None, None, "0.60", "60.00", "0.60", "each"),
            ("produce", "Lettuce tomato portions - 100 each", "100", "each", None, None, "1.00", "100.00", "1.00", "each"),
            ("cheese", "American cheese slices - 100 each", "100", "each", None, None, "0.40", "40.00", "0.40", "each"),
            ("veggie_patty", "Plant patties - 100 each", "100", "each", None, None, "1.60", "160.00", "1.60", "each"),
        ]
        new_lines = [
            ("beef", "GROUND CHUCK 80/20 - 2 CASES, 10 LB EACH", "2", "case", "10", "lb", "47.20", "94.40", "4.72", "lb"),
        ]
        for identifier, number, day, lines in [
            ("invoice_baseline", "DEMO-1001", "2026-11-01", baseline_lines),
            ("invoice_beef_increase", "DEMO-1002", "2026-11-07", new_lines),
        ]:
            total = str(sum((Decimal(line[7]) for line in lines), Decimal("0.00")))
            source = f"SYNTHETIC FIXTURE | Ridgeline Foodservice | {number} | {day}\n" + "\n".join(_invoice_line_text(line) for line in lines)
            source += f"\nSubtotal ${total}\nTax $0.00\nFreight $0.00\nTotal ${total}"
            document_id = f"doc_{identifier}"
            _document(connection, document_id, "invoice", source)
            _insert(connection, "invoices", id=identifier, document_id=document_id, vendor_id="ridgeline_foodservice",
                    vendor_name="Ridgeline Foodservice (fictional)", invoice_number=number, invoice_date=day,
                    currency="USD", subtotal=total, tax="0.00", freight="0.00", total=total)
            for ingredient, description, quantity, purchase_unit, pack_size, pack_unit, unit_price, line_total, unit_cost, base_unit in lines:
                line_id = f"line_{identifier}_{ingredient}"
                source_text = _invoice_line_text((ingredient, description, quantity, purchase_unit, pack_size, pack_unit, unit_price, line_total, unit_cost, base_unit))
                _insert(connection, "invoice_lines", id=line_id, invoice_id=identifier, ingredient_id=ingredient,
                        description=description, quantity=quantity, purchase_unit=purchase_unit, pack_size=pack_size,
                        pack_unit=pack_unit, unit_price=unit_price, line_total=line_total, source_page=1, source_text=source_text)
                _insert(connection, "ingredient_prices", id=f"price_{identifier}_{ingredient}", ingredient_id=ingredient,
                        invoice_line_id=line_id, effective_date=day, unit_cost=unit_cost, base_unit=base_unit)

        receipt_specs = [
            ("receipt_001", "DEMO-R001", "in_store", "2026-11-06T12:00:00-05:00", [("classic_burger", "2"), ("veggie_burger", "1")]),
            ("receipt_002", "DEMO-R002", "delivery", "2026-11-06T12:30:00-05:00", [("cheeseburger", "1"), ("classic_burger", "1")]),
            ("receipt_003", "DEMO-R003", "in_store", "2026-11-07T13:00:00-05:00", [("classic_burger", "1")]),
        ]
        for identifier, number, channel, sold_at, items in receipt_specs:
            document_id = f"doc_{identifier}"
            subtotal = sum((Decimal(recipes[dish][1]) * Decimal(quantity) for dish, quantity in items), Decimal("0.00"))
            tax = (subtotal * Decimal("0.08")).quantize(Decimal("0.01"))
            source = f"SYNTHETIC FIXTURE | Tartan Burger Co. | {number} | {sold_at} | {channel}\n"
            source += "\n".join(f"{quantity} x {recipes[dish][0]} @ ${recipes[dish][1]} = ${Decimal(recipes[dish][1]) * Decimal(quantity)}" for dish, quantity in items)
            source += f"\nSubtotal ${subtotal}\nDiscount $0.00\nTax ${tax}\nTip $0.00\nTotal ${subtotal + tax}"
            _document(connection, document_id, "receipt", source)
            _insert(connection, "receipts", id=identifier, document_id=document_id, receipt_number=number,
                    channel_id=channel, sold_at=sold_at, local_date=sold_at[:10], status="completed", currency="USD",
                    subtotal=str(subtotal), discount="0.00", tax=str(tax), tip="0.00", total=str(subtotal + tax))
            for index, (dish, quantity) in enumerate(items, start=1):
                unit_price = recipes[dish][1]
                gross = str(Decimal(unit_price) * Decimal(quantity))
                source_text = f"{quantity} x {recipes[dish][0]} @ ${unit_price} = ${gross}"
                _insert(connection, "receipt_items", id=f"item_{identifier}_{index}", receipt_id=identifier,
                        dish_id=dish, description=recipes[dish][0], quantity=quantity, unit_price=unit_price,
                        gross_amount=gross, discount_amount="0.00", net_amount=gross, source_page=1, source_text=source_text)
        for day, channel, status in [
            ("2026-11-06", "in_store", "complete"), ("2026-11-06", "delivery", "complete"),
            ("2026-11-07", "in_store", "partial"), ("2026-11-07", "delivery", "unknown"),
        ]:
            _insert(connection, "daily_coverage", date=day, channel_id=channel, status=status, updated_at=STAMP)
        _insert(connection, "seed_runs", name=SEED_NAME, applied_at=STAMP)
        return {"seeded": True, "restaurant_id": RESTAURANT_ID, "counts": _counts(connection)}


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m backend.marginguard.seed [--database path]."""
    import argparse

    from backend.config import Settings

    parser = argparse.ArgumentParser(description="Explicitly seed fictional MarginGuard checkpoint-one data into an empty database.")
    parser.add_argument("--database", type=Path, help="SQLite file path; defaults to MARGINGUARD_DATABASE_PATH from settings.")
    args = parser.parse_args(argv)
    path = args.database if args.database is not None else Settings().database_path
    try:
        summary = seed_demo(path)
    except (MigrationError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
