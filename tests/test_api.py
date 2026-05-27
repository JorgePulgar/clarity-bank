"""Tests de humo: la API arranca y los 5 endpoints responden con datos coherentes."""

from __future__ import annotations

import io

USER = "user_test"


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_transaction(client):
    r = client.post(
        "/transactions",
        json={
            "user_id": USER,
            "description": "PAGO TARJETA MERCADONA SL MADRID",
            "amount": -43.27,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["category"] == "alimentacion"
    assert 0.0 <= data["confidence"] <= 1.0
    assert data["classification_level"] in (1, 2)
    assert data["id"]


def test_anonymization_strips_pii(client):
    r = client.post(
        "/transactions",
        json={
            "user_id": USER,
            "description": "TRANSFERENCIA ES9121000418450200051332 juan@mail.com 612345678",
            "amount": -200.0,
        },
    )
    assert r.status_code == 201
    anon = r.json()["description_anonymized"]
    assert "ES9121000418450200051332" not in anon
    assert "juan@mail.com" not in anon
    assert "<IBAN>" in anon and "<EMAIL>" in anon


def test_list_transactions(client):
    client.post(
        "/transactions",
        json={
            "user_id": USER,
            "description": "NETFLIX SUSCRIPCION",
            "amount": -12.99,
        },
    )
    r = client.get(f"/transactions/{USER}")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_import_csv(client):
    csv_data = (
        "user_id,description,amount\n"
        f"{USER},LIDL SUPERMERCADOS,-22.5\n"
        f"{USER},REPSOL GASOLINERA,-55.0\n"
    )
    r = client.post(
        "/transactions/import",
        files={"file": ("batch.csv", io.BytesIO(csv_data.encode()), "text/csv")},
    )
    assert r.status_code == 200
    res = r.json()
    assert res["received"] == 2
    assert res["processed"] == 2


def test_user_stats(client):
    client.post(
        "/transactions",
        json={
            "user_id": USER,
            "description": "ABONO NOMINA EMPRESA SL",
            "amount": 1800.0,
        },
    )
    r = client.get(f"/users/{USER}/stats")
    assert r.status_code == 200
    s = r.json()
    assert s["user_id"] == USER
    assert s["n_transactions"] >= 1
    assert s["total_ingresos"] >= 1800.0


def test_generate_insight(client):
    client.post(
        "/transactions",
        json={
            "user_id": USER,
            "description": "MERCADONA",
            "amount": -30.0,
            "date": "2026-04-10T10:00:00",
        },
    )
    r = client.post("/insights/generate", json={"user_id": USER, "month": "2026-04"})
    assert r.status_code == 200
    data = r.json()
    assert data["source"] in ("llm", "template")
    assert data["text"]
