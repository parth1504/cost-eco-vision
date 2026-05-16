"""Basic smoke tests for the Order Processing API."""

import pytest
from fastapi.testclient import TestClient

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_list_orders():
    r = client.get("/api/v1/orders")
    assert r.status_code == 200
    assert "orders" in r.json()


def test_check_inventory():
    r = client.get("/api/v1/inventory/SKU-001")
    assert r.status_code == 200
    assert r.json()["sku"] == "SKU-001"
    assert r.json()["available"] > 0


def test_create_order():
    r = client.post("/api/v1/orders", json={
        "items": [{"sku": "SKU-001", "quantity": 1}],
        "total": 49.99,
        "payment_method": "card",
        "address": {"city": "New York", "zip": "10001"},
    })
    assert r.status_code in (200, 402, 409)


def test_metrics():
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "orders_today" in data
    assert "payment_success_rate" in data


def test_inventory_unknown_sku():
    r = client.get("/api/v1/inventory/SKU-999")
    assert r.status_code == 200
    assert r.json()["available"] == 0
