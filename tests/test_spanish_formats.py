import io
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def get_cookies():
    payload = {"email": "esformats@example.com", "password": "secret123", "full_name": "Formats"}
    response = client.post("/auth/register", json=payload)
    if response.status_code == 409:
        response = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert response.status_code == 200
    return response.cookies


def test_semicolon_csv_is_accepted():
    cookies = get_cookies()

    stripe_csv = """automatic_payout_id;balance_transaction_id;gross;fee;net;reporting_category;created;currency;description
po_es_1;btx_1;100.00;0.00;100.00;charge;2026-01-01T10:00:00Z;EUR;Payment
po_es_1;btx_2;0.00;-1.50;-1.50;fee;2026-01-01T10:01:00Z;EUR;Stripe fee
"""
    response = client.post(
        "/tools/reconcile-stripe",
        files={"file": ("stripe.csv", io.BytesIO(stripe_csv.encode("utf-8")), "text/csv")},
        cookies=cookies,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True