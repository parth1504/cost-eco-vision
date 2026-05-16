"""
Generate a realistic PR diff for testing PR Intelligence without GitHub.

Creates a diff that looks like a real code change to the order-processing-api,
which can be fed to the /intelligence/pr/analyze-diff endpoint.
"""

import json
import random
import sys

SIMULATED_DIFFS = [
    {
        "title": "Add retry logic with exponential backoff to payment service",
        "diff": """diff --git a/app/services.py b/app/services.py
index abc1234..def5678 100644
--- a/app/services.py
+++ b/app/services.py
@@ -45,6 +45,7 @@ class PaymentService:
     def __init__(self):
         self._transactions = []
         self._failure_rate = 0.02 if FAILURE_MODE == "normal" else 0.35
+        self._max_retries = 3
+        self._base_delay = 0.5

     def charge(self, amount: float, method: str, order_id: str) -> dict:
         start = time.time()
@@ -52,12 +53,28 @@ class PaymentService:

-        # Simulate network latency
-        latency = random.uniform(0.05, 0.3)
-        if FAILURE_MODE == "degraded":
-            latency = random.uniform(0.8, 3.5)
-
-        time.sleep(latency)
+        for attempt in range(self._max_retries + 1):
+            latency = random.uniform(0.05, 0.3)
+            if FAILURE_MODE == "degraded":
+                latency = random.uniform(0.8, 3.5)
+
+            time.sleep(latency)
+
+            if random.random() < self._failure_rate:
+                if attempt < self._max_retries:
+                    delay = self._base_delay * (2 ** attempt)
+                    logger.warning(
+                        f"Payment attempt {attempt+1} failed for order={order_id}, "
+                        f"retrying in {delay:.1f}s"
+                    )
+                    time.sleep(delay)
+                    continue
+                error = random.choice([
+                    "gateway_timeout",
+                    "insufficient_funds",
+                ])
+                return {"success": False, "error": error, "transaction_id": None}
+            break

         duration = (time.time() - start) * 1000
diff --git a/app/main.py b/app/main.py
index 111aaaa..222bbbb 100644
--- a/app/main.py
+++ b/app/main.py
@@ -89,6 +89,10 @@ async def create_order(payload: dict):
     if not payment_result["success"]:
         logger.error(
             f"Payment failed for order {order_id}: {payment_result['error']}"
+            f" after {payments._max_retries} retries"
         )
+        # Emit metric for payment failures
+        logger.info(f"METRIC payment_failure_total order={order_id} method={payload.get('payment_method')}")
         raise HTTPException(status_code=402, detail="Payment failed")
""",
    },
    {
        "title": "Add DynamoDB connection pooling and batch write",
        "diff": """diff --git a/app/services.py b/app/services.py
index abc1234..def5678 100644
--- a/app/services.py
+++ b/app/services.py
@@ -1,5 +1,7 @@
 import logging
 import os
+import threading
+from concurrent.futures import ThreadPoolExecutor
 from datetime import datetime

@@ -60,6 +62,8 @@ class InventoryService:
     def __init__(self):
+        self._pool = ThreadPoolExecutor(max_workers=20)
+        self._batch_buffer = []
+        self._buffer_lock = threading.Lock()
         self._stock = {
             "SKU-001": {"quantity": 150, "location": "us-east-1a"},

@@ -80,8 +84,22 @@ class InventoryService:
     def reserve(self, sku: str, quantity: int):
-        if sku in self._stock:
-            self._stock[sku]["quantity"] = max(0, self._stock[sku]["quantity"] - quantity)
+        with self._buffer_lock:
+            self._batch_buffer.append({"sku": sku, "quantity": quantity})
+            if len(self._batch_buffer) >= 25:
+                self._flush_batch()
+
+    def _flush_batch(self):
+        items = self._batch_buffer[:]
+        self._batch_buffer = []
+        try:
+            for item in items:
+                sku = item["sku"]
+                if sku in self._stock:
+                    self._stock[sku]["quantity"] = max(0, self._stock[sku]["quantity"] - item["quantity"])
+            logger.info(f"Batch write completed items={len(items)}")
+        except Exception as e:
+            logger.error(f"Batch write failed: {e} items_lost={len(items)}")
+            raise
diff --git a/terraform/main.tf b/terraform/main.tf
index aaa1111..bbb2222 100644
--- a/terraform/main.tf
+++ b/terraform/main.tf
@@ -50,6 +50,16 @@ resource "aws_iam_role_policy" "dynamodb_access" {
+resource "aws_dynamodb_table" "inventory" {
+  name         = "order-processing-api-inventory"
+  billing_mode = "PAY_PER_REQUEST"
+  hash_key     = "sku"
+
+  attribute {
+    name = "sku"
+    type = "S"
+  }
+}
""",
    },
    {
        "title": "Fix memory leak in log generator background thread",
        "diff": """diff --git a/app/log_generator.py b/app/log_generator.py
index aaa1111..bbb2222 100644
--- a/app/log_generator.py
+++ b/app/log_generator.py
@@ -25,6 +25,7 @@ class LogGenerator:
     def __init__(self):
         self._running = False
         self._thread = None
+        self._event_buffer = []
+        self._max_buffer = 1000

     def start_background_patterns(self):
@@ -35,6 +37,15 @@ class LogGenerator:
     def stop(self):
         self._running = False
+        self._event_buffer.clear()
+
+    def _check_buffer(self):
+        if len(self._event_buffer) > self._max_buffer:
+            dropped = len(self._event_buffer) - self._max_buffer
+            self._event_buffer = self._event_buffer[-self._max_buffer:]
+            logger.warning(f"Event buffer overflow, dropped {dropped} events")

     def _run_cycle(self):
         while self._running:
+            self._check_buffer()
             elapsed = time.time() - self._phase_start
""",
    },
]


def generate_pr_diff(index: int = None) -> dict:
    if index is None:
        index = random.randint(0, len(SIMULATED_DIFFS) - 1)
    return SIMULATED_DIFFS[index % len(SIMULATED_DIFFS)]


if __name__ == "__main__":
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else None
    pr = generate_pr_diff(idx)
    print(json.dumps(pr, indent=2))
