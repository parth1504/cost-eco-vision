"""
CloudOps Demo Application — Order Processing API

A realistic microservice that processes orders, manages inventory,
and communicates with external payment/shipping services.
Generates authentic CloudWatch log patterns including:
- Normal request/response cycles
- Intermittent failures (DB timeouts, upstream 5xx)
- Cascading errors (payment gateway → order failure → retry storms)
- Performance degradation patterns
"""

import logging
import os
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from log_generator import LogGenerator
from services import (
    InventoryService,
    OrderService,
    PaymentService,
    ShippingService,
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
APP_ENV = os.getenv("APP_ENV", "production")
INSTANCE_ID = os.getenv("INSTANCE_ID", "i-demo-001")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("order-api")

log_gen = LogGenerator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Order Processing API on {INSTANCE_ID} env={APP_ENV}")
    log_gen.start_background_patterns()
    yield
    logger.info("Shutting down Order Processing API")
    log_gen.stop()


app = FastAPI(
    title="Order Processing API",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

inventory = InventoryService()
orders = OrderService()
payments = PaymentService()
shipping = ShippingService()


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.time()

    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"client={request.client.host if request.client else 'unknown'}"
    )

    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    logger.info(
        f"[{request_id}] completed status={response.status_code} "
        f"duration={duration_ms:.1f}ms"
    )

    if duration_ms > 2000:
        logger.warning(
            f"[{request_id}] SLOW REQUEST {request.url.path} "
            f"took {duration_ms:.0f}ms (threshold=2000ms)"
        )

    return response


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "instance": INSTANCE_ID,
        "version": "2.1.0",
        "uptime_seconds": int(time.time() - app.state.start_time)
        if hasattr(app.state, "start_time")
        else 0,
    }


@app.get("/api/v1/orders")
async def list_orders(page: int = 1, limit: int = 20):
    return orders.list_orders(page, limit)


@app.post("/api/v1/orders")
async def create_order(payload: dict):
    order_id = str(uuid.uuid4())
    logger.info(f"Creating order {order_id} items={len(payload.get('items', []))}")

    # Check inventory
    for item in payload.get("items", []):
        available = inventory.check_stock(item["sku"])
        if not available:
            logger.warning(
                f"Order {order_id} failed: SKU {item['sku']} out of stock"
            )
            raise HTTPException(status_code=409, detail=f"SKU {item['sku']} unavailable")

    # Process payment
    payment_result = payments.charge(
        amount=payload.get("total", 0),
        method=payload.get("payment_method", "card"),
        order_id=order_id,
    )

    if not payment_result["success"]:
        logger.error(
            f"Payment failed for order {order_id}: {payment_result['error']}"
        )
        raise HTTPException(status_code=402, detail="Payment failed")

    # Create order record
    order = orders.create(order_id, payload, payment_result["transaction_id"])
    logger.info(f"Order {order_id} created successfully total=${payload.get('total', 0)}")

    # Reserve inventory
    for item in payload.get("items", []):
        inventory.reserve(item["sku"], item.get("quantity", 1))

    return {"order_id": order_id, "status": "confirmed", **order}


@app.get("/api/v1/orders/{order_id}")
async def get_order(order_id: str):
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.post("/api/v1/orders/{order_id}/ship")
async def ship_order(order_id: str):
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    logger.info(f"Initiating shipment for order {order_id}")
    result = shipping.create_shipment(order_id, order.get("address", {}))

    if not result["success"]:
        logger.error(f"Shipping failed for {order_id}: {result['error']}")
        raise HTTPException(status_code=503, detail="Shipping service unavailable")

    orders.update_status(order_id, "shipped", tracking=result["tracking_id"])
    logger.info(f"Order {order_id} shipped tracking={result['tracking_id']}")
    return {"status": "shipped", "tracking_id": result["tracking_id"]}


@app.get("/api/v1/inventory/{sku}")
async def check_inventory(sku: str):
    stock = inventory.get_stock(sku)
    return {"sku": sku, "available": stock["quantity"], "warehouse": stock["location"]}


@app.post("/api/v1/inventory/restock")
async def restock(payload: dict):
    sku = payload.get("sku")
    quantity = payload.get("quantity", 0)
    logger.info(f"Restocking SKU {sku} qty={quantity}")
    inventory.restock(sku, quantity)
    return {"sku": sku, "restocked": quantity}


@app.get("/api/v1/metrics")
async def get_metrics():
    return {
        "orders_today": orders.count_today(),
        "revenue_today": orders.revenue_today(),
        "inventory_alerts": inventory.low_stock_count(),
        "payment_success_rate": payments.success_rate(),
        "avg_response_ms": random.uniform(45, 180),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
