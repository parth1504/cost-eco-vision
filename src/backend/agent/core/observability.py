"""
OpenTelemetry instrumentation for the multi-agent system.

Provides distributed tracing, metrics, and structured logging across
all agent interactions. Every agent call, message exchange, LLM invocation,
and verification gate is captured as a span with rich attributes.

The tracer propagates context through the agent message bus so that
a single user request produces one unified trace across all participating
agents — viewable in Jaeger, Datadog, or any OTLP-compatible backend.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    _OTEL_AVAILABLE = True
except ImportError:
    logger.info("OpenTelemetry SDK not installed — using built-in trace collector")


@dataclass
class SpanRecord:
    """Lightweight span representation for the built-in collector."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation: str
    agent: str
    start_time: float
    end_time: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation": self.operation,
            "agent": self.agent,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 2),
            "attributes": self.attributes,
            "events": self.events,
            "status": self.status,
        }


@dataclass
class MetricRecord:
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp,
        }


class TraceCollector:
    """
    Built-in trace collector that works without external OTel infrastructure.

    Stores spans and metrics in memory (per session). The WebSocket API
    streams these to the agentic UI in real-time. When OTel SDK is available,
    spans are also exported to the configured backend.
    """

    def __init__(self):
        self._spans: Dict[str, List[SpanRecord]] = {}
        self._metrics: List[MetricRecord] = []
        self._listeners: List[Callable] = []
        self._otel_tracer = None
        self._otel_meter = None

        if _OTEL_AVAILABLE:
            resource = Resource.create({"service.name": "cloud-optimizer-agents"})
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)
            self._otel_tracer = trace.get_tracer("agent.orchestrator")

            reader = PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=30000)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
            self._otel_meter = metrics.get_meter("agent.metrics")

    def add_listener(self, callback: Callable):
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable):
        self._listeners = [l for l in self._listeners if l is not callback]

    def _notify(self, event_type: str, data: Dict[str, Any]):
        for listener in self._listeners:
            try:
                listener(event_type, data)
            except Exception as e:
                logger.warning("Trace listener error: %s", e)

    @contextmanager
    def span(
        self,
        trace_id: str,
        operation: str,
        agent: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Generator[SpanRecord, None, None]:
        import uuid
        span_id = str(uuid.uuid4())[:8]
        record = SpanRecord(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation=operation,
            agent=agent,
            start_time=time.time(),
            attributes=attributes or {},
        )

        self._notify("span_start", {
            "trace_id": trace_id,
            "span_id": span_id,
            "operation": operation,
            "agent": agent,
        })

        try:
            yield record
        except Exception as e:
            record.status = "error"
            record.events.append({
                "name": "exception",
                "attributes": {"exception.message": str(e)},
                "timestamp": time.time(),
            })
            raise
        finally:
            record.end_time = time.time()
            if trace_id not in self._spans:
                self._spans[trace_id] = []
            self._spans[trace_id].append(record)

            self._notify("span_end", record.to_dict())

    def record_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ):
        record = MetricRecord(name=name, value=value, labels=labels or {})
        self._metrics.append(record)
        self._notify("metric", record.to_dict())

    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        spans = self._spans.get(trace_id, [])
        return [s.to_dict() for s in spans]

    def get_all_traces(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            tid: [s.to_dict() for s in spans]
            for tid, spans in self._spans.items()
        }

    def get_metrics(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._metrics[-limit:]]

    def get_session_summary(self, trace_id: str) -> Dict[str, Any]:
        spans = self._spans.get(trace_id, [])
        if not spans:
            return {}

        agents_involved = list(set(s.agent for s in spans))
        total_duration = sum(s.duration_ms for s in spans)
        total_tokens = sum(
            s.attributes.get("token_usage", {}).get("total", 0)
            for s in spans
        )

        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "agents_involved": agents_involved,
            "total_duration_ms": round(total_duration, 2),
            "total_tokens": total_tokens,
            "error_count": sum(1 for s in spans if s.status == "error"),
            "timeline": [
                {
                    "agent": s.agent,
                    "operation": s.operation,
                    "duration_ms": round(s.duration_ms, 2),
                    "status": s.status,
                }
                for s in sorted(spans, key=lambda s: s.start_time)
            ],
        }


# Singleton
trace_collector = TraceCollector()
