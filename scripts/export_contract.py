"""Export OpenAPI and read/calculation examples using an isolated small demo DB.

Run with the venv: python scripts/export_contract.py
Does not inspect or modify your configured business database or API credentials.
"""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.marginguard.seed import seed_demo


def main():
    docs = ROOT / "docs"
    examples = ROOT / "examples" / "api"
    examples.mkdir(parents=True, exist_ok=True)
    settings = Settings(_env_file=None, ai_mode="mock", database_path=ROOT / "data" / "unused.db")
    app = create_app(settings)
    (docs / "openapi.json").write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="marginguard-contract-") as directory:
        database = Path(directory) / "examples.db"
        seed_demo(database)
        app = create_app(Settings(_env_file=None, ai_mode="mock", database_path=database))
        with TestClient(app) as client:
            paths = {
                "restaurant": "/api/restaurant", "catalog": "/api/catalog",
                "documents": "/api/documents", "document-detail": "/api/documents/doc_invoice_beef_increase",
                "invoices": "/api/invoices", "receipts": "/api/receipts",
                "coverage": "/api/coverage", "ingredient-prices": "/api/ingredients/beef/prices",
                "alerts": "/api/alerts", "capabilities": "/api/capabilities",
                "sales": "/api/sales?as_of=2026-11-07",
                "dish-cost": "/api/dishes/classic_burger/cost?as_of=2026-11-07",
                "dashboard": "/api/dashboard?as_of=2026-11-07",
            }
            for name, path in paths.items():
                response = client.get(path)
                response.raise_for_status()
                (examples / f"{name}.json").write_text(json.dumps(response.json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Updated docs/openapi.json and examples/api/*.json from the running contract.")


if __name__ == "__main__":
    main()
