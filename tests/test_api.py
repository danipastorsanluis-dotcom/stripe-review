import io

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def auth_cookies(email: str = "test@example.com", password: str = "secret123"):
    payload = {"email": email, "password": password, "full_name": "Test User"}
    response = client.post("/auth/register", json=payload)
    if response.status_code == 409:
        response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.cookies


def test_root_works():
    response = client.get("/")
    assert response.status_code == 200


def test_health_works():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "healthy"


def test_reconcile_without_auth_returns_401():
    """Sin cookie de sesión, todos los endpoints protegidos devuelven 401."""
    csv_content = "automatic_payout_id,balance_transaction_id,gross,fee,net,reporting_category,created,currency,description\npo_x,btx_1,100.00,0.00,100.00,charge,2026-01-01T10:00:00Z,EUR,Payment\n"
    response = client.post(
        "/tools/reconcile-stripe",
        files={"file": ("x.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 401


def test_client_list_without_auth_returns_401():
    response = client.get("/clients")
    assert response.status_code == 401


def test_download_without_auth_returns_401():
    response = client.get("/tools/download/reconciliation/1")
    assert response.status_code == 401


def test_password_too_short_rejected():
    """Passwords con menos de 8 caracteres se rechazan en registro."""
    response = client.post(
        "/auth/register",
        json={"email": "short@example.com", "password": "short", "full_name": ""},
    )
    assert response.status_code in (400, 422)


def test_login_wrong_password_returns_401():
    auth_cookies(email="wrong@example.com", password="correctpass123")
    response = client.post(
        "/auth/login",
        json={"email": "wrong@example.com", "password": "incorrect123"},
    )
    assert response.status_code == 401


def test_client_crud_and_reconcile_flow():
    cookies = auth_cookies()
    client_create = client.post(
        "/clients",
        json={"name": "Panadería López SL", "nif": "B12345678"},
        cookies=cookies,
    )
    assert client_create.status_code == 200
    client_id = client_create.json()["item"]["id"]

    csv_content = """automatic_payout_id,balance_transaction_id,gross,fee,net,reporting_category,created,currency,description
po_test_1,btx_1,100.00,0.00,100.00,charge,2026-01-01T10:00:00Z,EUR,Payment
po_test_1,btx_2,0.00,-1.50,-1.50,fee,2026-01-01T10:01:00Z,EUR,Stripe fee
po_test_1,btx_3,-10.00,0.00,-10.00,refund,2026-01-01T10:02:00Z,EUR,Refund
"""

    response = client.post(
        "/tools/reconcile-stripe",
        data={"client_id": str(client_id)},
        files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        cookies=cookies,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["can_export_accounting"] is True
    run_id = body["run_id"]

    # Usuario correcto puede descargar su propio run
    dl = client.get(f"/tools/download/reconciliation/{run_id}", cookies=cookies)
    assert dl.status_code == 200

    history = client.get(f"/clients/{client_id}", cookies=cookies)
    assert history.status_code == 200
    assert len(history.json()["runs"]) >= 1


def test_cross_user_data_leak_blocked():
    """
    Un usuario autenticado no puede descargar los archivos de OTRO usuario.
    Este es el fix del data leak: fetch_artifact_path ahora filtra por user_id.
    """
    # Usuario A crea un run
    cookies_a = auth_cookies(email="user_a@example.com", password="secretA1234")
    csv_content = "automatic_payout_id,balance_transaction_id,gross,fee,net,reporting_category,created,currency,description\npo_a,btx_1,100.00,0.00,100.00,charge,2026-01-01T10:00:00Z,EUR,Payment\n"
    response = client.post(
        "/tools/reconcile-stripe",
        files={"file": ("a.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        cookies=cookies_a,
    )
    assert response.status_code == 200
    run_id_a = response.json()["run_id"]

    # Usuario B intenta descargar el run de A
    cookies_b = auth_cookies(email="user_b@example.com", password="secretB1234")
    intrusion = client.get(f"/tools/download/reconciliation/{run_id_a}", cookies=cookies_b)
    assert intrusion.status_code == 404, (
        "DATA LEAK: Usuario B no debería poder descargar runs de usuario A"
    )


def test_billing_simulate_upgrade_disabled_by_default():
    """
    /billing/simulate-upgrade solo debe funcionar con ENABLE_BILLING_SIMULATION=true
    Y APP_ENV=development. Por defecto devuelve 404.
    """
    cookies = auth_cookies()
    response = client.post("/billing/simulate-upgrade/plus", cookies=cookies)
    # Debe ser 404 salvo que se active el flag explícito
    assert response.status_code == 404


def test_clean_stripe_csv_returns_200():
    cookies = auth_cookies()
    csv_content = """automatic_payout_id,balance_transaction_id,gross,fee,net,reporting_category,created,currency,description
po_clean_1,btx_1,100.00,0.00,100.00,charge,2026-01-01T10:00:00Z,EUR,Payment
po_clean_1,btx_2,0.00,-1.50,-1.50,fee,2026-01-01T10:01:00Z,EUR,Stripe fee
"""
    response = client.post(
        "/tools/clean-stripe-csv",
        files={"file": ("clean.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        cookies=cookies,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_logout_invalidates_session():
    cookies = auth_cookies(email="logout_user@example.com", password="secret123")
    # Con cookie válida /auth/me funciona
    me1 = client.get("/auth/me", cookies=cookies)
    assert me1.status_code == 200

    # Logout borra la sesión
    logout = client.post("/auth/logout", cookies=cookies)
    assert logout.status_code == 200

    # El mismo token ya no es válido
    me2 = client.get("/auth/me", cookies=cookies)
    assert me2.status_code == 401
