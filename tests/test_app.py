import base64
import json
from datetime import date
from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

from main import create_app
from receipt_reader import ExtractedReceipt, read_receipt


def make_client(tmp_path, monkeypatch):
    monkeypatch.delenv("STORE_RECEIPT_IMAGES", raising=False)
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    return TestClient(app)


def sample_receipt(**overrides):
    receipt = {
        "store_name": "Corner Market",
        "purchase_date": "2025-03-14",
        "total_amount": 8.5,
        "items": [
            {
                "name": "Apples",
                "quantity": 2,
                "unit_price": 2.25,
                "total_price": 4.5,
            },
            {
                "name": "Milk",
                "quantity": 1,
                "unit_price": 4,
                "total_price": 4,
            },
        ],
    }
    receipt.update(overrides)
    return receipt


def test_saves_receipt_and_links_quantities_to_items(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)

    response = client.post("/api/receipts", json=sample_receipt())

    assert response.status_code == 201
    saved = response.json()
    assert saved["purchase_date"] == "2025-03-14"
    assert saved["items"][0]["name"] == "Apples"
    assert float(saved["items"][0]["quantity"]) == 2
    assert saved["items"][0]["id"]

    history = client.get("/api/receipts").json()
    assert len(history) == 1
    assert history[0]["id"] == saved["id"]


def test_item_search_and_monthly_spending(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    client.post("/api/receipts", json=sample_receipt())

    items = client.get("/api/items", params={"q": "apple"}).json()
    spending = client.get("/api/spending", params={"month": "2025-03"}).json()

    assert len(items) == 1
    assert items[0]["purchase_date"] == "2025-03-14"
    assert float(spending["total"]) == 8.5


def test_rejects_receipt_without_items(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)

    response = client.post("/api/receipts", json=sample_receipt(items=[]))

    assert response.status_code == 422


def test_receipt_image_is_not_saved_by_default(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/receipts",
        json=sample_receipt(image_data=base64.b64encode(b"receipt image").decode()),
    )

    assert response.status_code == 400


def test_receipt_image_is_stored_only_when_enabled(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setenv("STORE_RECEIPT_IMAGES", "true")
    encoded_image = base64.b64encode(b"opted-in receipt image").decode()

    response = client.post(
        "/api/receipts",
        json=sample_receipt(image_data=encoded_image),
    )

    assert response.status_code == 201
    db = client.app.state.session_factory()
    try:
        from models import Receipt

        assert db.get(Receipt, response.json()["id"]).image_data == b"opted-in receipt image"
    finally:
        db.close()


def test_reader_uses_structured_output_and_flags_missing_date(monkeypatch):
    image_buffer = BytesIO()
    Image.new("RGB", (2000, 1000), "white").save(image_buffer, format="JPEG")
    response_text = json.dumps(
        {
            "store_name": "Corner Market",
            "purchase_date": None,
            "items": [
                {"name": "Apples", "quantity": 2, "unit_price": 2, "total_price": 4}
            ],
            "total_amount": 4,
            "image_readable": True,
        }
    )

    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["config"].response_mime_type == "application/json"
            assert kwargs["config"].response_schema is ExtractedReceipt
            resized = Image.open(BytesIO(kwargs["contents"][0].inline_data.data))
            assert max(resized.size) == 1600
            return SimpleNamespace(text=response_text)

    monkeypatch.setattr(
        "receipt_reader._client",
        lambda: (SimpleNamespace(models=FakeModels()), "test-model"),
    )

    result = read_receipt(image_buffer.getvalue())

    assert result["date_needs_confirmation"] is True
    assert result["purchase_date"] == date.today()
    assert result["items"][0]["name"] == "Apples"


def test_frontend_is_served(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)

    response = client.get("/")

    assert response.status_code == 200
    assert "Scan receipt" in response.text
