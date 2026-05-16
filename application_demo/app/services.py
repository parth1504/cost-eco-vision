"""
Simulated backend services with realistic failure modes.

Each service has configurable failure rates that can be toggled
to simulate production incidents (payment gateway timeouts,
DB connection pool exhaustion, shipping API rate limits).
"""

import logging
import os
import random
import time
import uuid
from datetime import datetime, timedelta

logger = logging.getLogger("order-api.services")

FAILURE_MODE = os.getenv("FAILURE_MODE", "normal")


class PaymentService:
    def __init__(self):
        self._transactions = []
        self._failure_rate = 0.02 if FAILURE_MODE == "normal" else 0.35

    def charge(self, amount: float, method: str, order_id: str) -> dict:
        start = time.time()
        tx_id = f"txn_{uuid.uuid4().hex[:12]}"

        # Simulate network latency
        latency = random.uniform(0.05, 0.3)
        if FAILURE_MODE == "degraded":
            latency = random.uniform(0.8, 3.5)

        time.sleep(latency)

        if random.random() < self._failure_rate:
            error = random.choice([
                "gateway_timeout",
                "insufficient_funds",
                "card_declined",
                "fraud_detected",
                "rate_limit_exceeded",
            ])
            logger.error(
                f"Payment charge failed order={order_id} amount={amount} "
                f"error={error} latency={latency*1000:.0f}ms"
            )
            return {"success": False, "error": error, "transaction_id": None}

        duration = (time.time() - start) * 1000
        logger.info(
            f"Payment charged order={order_id} amount=${amount:.2f} "
            f"tx={tx_id} method={method} duration={duration:.0f}ms"
        )

        self._transactions.append({
            "id": tx_id,
            "amount": amount,
            "order_id": order_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        return {"success": True, "transaction_id": tx_id, "error": None}

    def success_rate(self) -> float:
        if not self._transactions:
            return 99.5
        return round(100 - (self._failure_rate * 100), 1)


class InventoryService:
    def __init__(self):
        self._stock = {
            "SKU-001": {"quantity": 150, "location": "us-east-1a", "name": "Widget Pro"},
            "SKU-002": {"quantity": 45, "location": "us-east-1b", "name": "Gadget Plus"},
            "SKU-003": {"quantity": 0, "location": "us-west-2a", "name": "Connector XL"},
            "SKU-004": {"quantity": 890, "location": "us-east-1a", "name": "Cable Standard"},
            "SKU-005": {"quantity": 12, "location": "us-west-2b", "name": "Adapter Mini"},
        }
        self._db_failure_rate = 0.01 if FAILURE_MODE == "normal" else 0.15

    def check_stock(self, sku: str) -> bool:
        if random.random() < self._db_failure_rate:
            logger.error(
                f"DynamoDB timeout checking stock for {sku} "
                f"ProvisionedThroughputExceededException"
            )
            raise Exception("Database timeout")

        item = self._stock.get(sku)
        if not item:
            return False
        return item["quantity"] > 0

    def get_stock(self, sku: str) -> dict:
        return self._stock.get(sku, {"quantity": 0, "location": "unknown"})

    def reserve(self, sku: str, quantity: int):
        if sku in self._stock:
            self._stock[sku]["quantity"] = max(0, self._stock[sku]["quantity"] - quantity)
            logger.debug(f"Reserved {quantity}x {sku}, remaining={self._stock[sku]['quantity']}")

    def restock(self, sku: str, quantity: int):
        if sku in self._stock:
            self._stock[sku]["quantity"] += quantity
        else:
            self._stock[sku] = {"quantity": quantity, "location": "us-east-1a", "name": sku}

    def low_stock_count(self) -> int:
        return sum(1 for v in self._stock.values() if v["quantity"] < 20)


class OrderService:
    def __init__(self):
        self._orders = {}

    def create(self, order_id: str, payload: dict, transaction_id: str) -> dict:
        order = {
            "id": order_id,
            "items": payload.get("items", []),
            "total": payload.get("total", 0),
            "status": "confirmed",
            "transaction_id": transaction_id,
            "address": payload.get("address", {}),
            "created_at": datetime.utcnow().isoformat(),
        }
        self._orders[order_id] = order
        return order

    def get(self, order_id: str) -> dict | None:
        return self._orders.get(order_id)

    def update_status(self, order_id: str, status: str, **kwargs):
        if order_id in self._orders:
            self._orders[order_id]["status"] = status
            self._orders[order_id].update(kwargs)

    def list_orders(self, page: int, limit: int) -> dict:
        all_orders = list(self._orders.values())
        start = (page - 1) * limit
        return {
            "orders": all_orders[start:start + limit],
            "total": len(all_orders),
            "page": page,
        }

    def count_today(self) -> int:
        return len(self._orders)

    def revenue_today(self) -> float:
        return sum(o.get("total", 0) for o in self._orders.values())


class ShippingService:
    def __init__(self):
        self._failure_rate = 0.03 if FAILURE_MODE == "normal" else 0.40

    def create_shipment(self, order_id: str, address: dict) -> dict:
        latency = random.uniform(0.1, 0.5)
        if FAILURE_MODE == "degraded":
            latency = random.uniform(1.0, 5.0)

        time.sleep(latency)

        if random.random() < self._failure_rate:
            error = random.choice([
                "carrier_unavailable",
                "address_validation_failed",
                "rate_limit_exceeded",
                "service_timeout",
            ])
            logger.error(
                f"Shipping API error order={order_id} error={error} "
                f"latency={latency*1000:.0f}ms"
            )
            return {"success": False, "error": error, "tracking_id": None}

        tracking = f"TRK{random.randint(100000000, 999999999)}"
        logger.info(f"Shipment created order={order_id} tracking={tracking}")
        return {"success": True, "tracking_id": tracking, "error": None}
