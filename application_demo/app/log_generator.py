"""
Realistic Log Pattern Generator

Runs background threads that produce authentic log patterns:
- Normal operation: steady request flow, health checks, metrics collection
- Degradation: increasing latency, connection pool warnings, retry attempts
- Incident: error cascades, circuit breaker trips, failover events
- Recovery: gradual return to normal, backlog processing

Patterns cycle automatically to give the Engineering Intelligence system
real data to analyze and correlate.
"""

import logging
import os
import random
import threading
import time
from datetime import datetime

logger = logging.getLogger("order-api")
infra_logger = logging.getLogger("order-api.infra")
db_logger = logging.getLogger("order-api.database")
cache_logger = logging.getLogger("order-api.cache")

CYCLE_MINUTES = int(os.getenv("LOG_CYCLE_MINUTES", "30"))


class LogGenerator:
    def __init__(self):
        self._running = False
        self._thread = None
        self._phase = "normal"
        self._phase_start = time.time()

    def start_background_patterns(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_cycle, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run_cycle(self):
        """Cycle through operational phases producing realistic log patterns."""
        while self._running:
            elapsed = time.time() - self._phase_start
            cycle_seconds = CYCLE_MINUTES * 60

            # Phase progression: normal(60%) → degradation(15%) → incident(10%) → recovery(15%)
            progress = (elapsed % cycle_seconds) / cycle_seconds

            if progress < 0.60:
                self._emit_normal()
                time.sleep(random.uniform(2, 8))
            elif progress < 0.75:
                self._emit_degradation()
                time.sleep(random.uniform(1, 4))
            elif progress < 0.85:
                self._emit_incident()
                time.sleep(random.uniform(0.5, 2))
            else:
                self._emit_recovery()
                time.sleep(random.uniform(2, 6))

    def _emit_normal(self):
        """Normal operation logs — what healthy production looks like."""
        patterns = [
            lambda: logger.info(
                f"Health check passed cpu=12% mem=45% connections=23/100"
            ),
            lambda: db_logger.info(
                f"Query executed table=orders duration={random.randint(2, 45)}ms rows={random.randint(1, 50)}"
            ),
            lambda: cache_logger.info(
                f"Cache hit key=inventory:{random.choice(['SKU-001','SKU-002','SKU-004'])} ttl=298s"
            ),
            lambda: infra_logger.info(
                f"Connection pool status active=5 idle=15 max=100 wait_time=0ms"
            ),
            lambda: logger.info(
                f"Scheduled task completed task=metrics_export records={random.randint(100, 500)} duration={random.randint(50, 200)}ms"
            ),
            lambda: logger.info(
                f"Request processed path=/api/v1/orders method=GET status=200 duration={random.randint(15, 120)}ms"
            ),
            lambda: cache_logger.debug(
                f"Cache refresh key=product_catalog entries={random.randint(200, 400)}"
            ),
        ]
        random.choice(patterns)()

    def _emit_degradation(self):
        """Performance degradation — the warning signs before an incident."""
        patterns = [
            lambda: logger.warning(
                f"Elevated response time path=/api/v1/orders/create "
                f"duration={random.randint(1500, 4000)}ms threshold=2000ms"
            ),
            lambda: db_logger.warning(
                f"Connection pool nearing capacity active={random.randint(75, 95)} "
                f"max=100 wait_queue={random.randint(3, 15)}"
            ),
            lambda: infra_logger.warning(
                f"Memory pressure detected used={random.randint(78, 92)}% "
                f"gc_pauses={random.randint(3, 8)} last_gc_ms={random.randint(100, 500)}"
            ),
            lambda: cache_logger.warning(
                f"Cache miss rate elevated rate={random.uniform(0.15, 0.45):.2f} "
                f"evictions={random.randint(50, 200)}/min"
            ),
            lambda: logger.warning(
                f"Upstream latency spike service=payment-gateway "
                f"p99={random.randint(2000, 8000)}ms normal_p99=200ms"
            ),
            lambda: db_logger.warning(
                f"Query slow query=SELECT_ORDERS duration={random.randint(800, 3000)}ms "
                f"rows_scanned={random.randint(10000, 50000)}"
            ),
            lambda: infra_logger.warning(
                f"Thread pool saturation worker_threads={random.randint(45, 50)}/50 "
                f"queued_tasks={random.randint(10, 40)}"
            ),
        ]
        random.choice(patterns)()

    def _emit_incident(self):
        """Active incident — errors cascading through the system."""
        patterns = [
            lambda: logger.error(
                f"Request failed path=/api/v1/orders method=POST status=500 "
                f"error=ConnectionPoolExhausted active=100/100 wait_timeout=30000ms"
            ),
            lambda: db_logger.error(
                f"DynamoDB ProvisionedThroughputExceededException "
                f"table=Orders consumed_wcu={random.randint(500, 1000)} provisioned_wcu=200"
            ),
            lambda: logger.error(
                f"Payment gateway timeout order_id={random.randbytes(4).hex()} "
                f"timeout=30000ms retries=3 circuit_breaker=OPEN"
            ),
            lambda: infra_logger.error(
                f"Circuit breaker OPEN service=payment-gateway "
                f"failures={random.randint(15, 30)}/10 threshold=5 cooldown=60s"
            ),
            lambda: logger.error(
                f"Retry storm detected endpoint=/api/v1/orders/create "
                f"retry_count={random.randint(50, 200)} window=60s "
                f"source=client_retry_amplification"
            ),
            lambda: db_logger.error(
                f"Transaction conflict ConditionalCheckFailedException "
                f"table=Inventory item=SKU-{random.randint(1,5):03d} "
                f"concurrent_writes={random.randint(5, 20)}"
            ),
            lambda: logger.critical(
                f"Service degraded below SLA error_rate={random.uniform(15, 45):.1f}% "
                f"threshold=5% duration={random.randint(60, 300)}s "
                f"affected_customers={random.randint(50, 500)}"
            ),
            lambda: infra_logger.error(
                f"Health check FAILING consecutive_failures={random.randint(3, 10)} "
                f"last_error=ConnectionRefused target=localhost:8080"
            ),
        ]
        random.choice(patterns)()

    def _emit_recovery(self):
        """Recovery phase — system stabilizing after incident."""
        patterns = [
            lambda: logger.info(
                f"Circuit breaker HALF-OPEN service=payment-gateway "
                f"probe_success=True next_full_open_in=30s"
            ),
            lambda: infra_logger.info(
                f"Connection pool recovering active={random.randint(30, 60)} "
                f"max=100 draining_stale={random.randint(5, 15)}"
            ),
            lambda: logger.info(
                f"Backlog processing remaining={random.randint(20, 100)} "
                f"rate={random.randint(10, 30)}/s eta={random.randint(5, 30)}s"
            ),
            lambda: db_logger.info(
                f"Throughput normalized consumed_wcu={random.randint(80, 180)} "
                f"provisioned_wcu=200 throttle_count=0"
            ),
            lambda: cache_logger.info(
                f"Cache warming completed entries={random.randint(200, 500)} "
                f"hit_rate={random.uniform(0.85, 0.98):.2f}"
            ),
            lambda: logger.info(
                f"Error rate stabilizing current={random.uniform(1, 4.5):.1f}% "
                f"target=<5% trend=decreasing"
            ),
        ]
        random.choice(patterns)()
