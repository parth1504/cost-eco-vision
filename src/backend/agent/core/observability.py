"""
Observability layer: LangSmith + OpenTelemetry.

LangSmith provides:
  - Automatic LLM call tracing (prompts, completions, token usage)
  - LangGraph execution traces (node transitions, state snapshots)
  - Run history, latency analysis, error tracking
  - UI at smith.langchain.com for debugging agent behavior

OpenTelemetry provides:
  - Infrastructure-level distributed tracing (API latency, DB calls)
  - Custom metrics (recommendation counts, processing durations)
  - Export to Jaeger, Datadog, Grafana, or any OTLP backend

Both work simultaneously — LangSmith for LLM/agent debugging,
OpenTelemetry for infrastructure monitoring.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LangSmith configuration
# ---------------------------------------------------------------------------

def configure_langsmith(
    api_key: Optional[str] = None,
    project: str = "cloud-optimizer-agents",
    tracing_enabled: bool = True,
):
    """
    Configure LangSmith tracing. Call at app startup.

    LangGraph automatically sends traces to LangSmith when these
    environment variables are set. No code changes needed in the graph.
    """
    if api_key:
        os.environ["LANGCHAIN_API_KEY"] = api_key

    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true" if tracing_enabled else "false")
    os.environ.setdefault("LANGCHAIN_PROJECT", project)

    if os.environ.get("LANGCHAIN_API_KEY"):
        logger.info("LangSmith tracing enabled — project: %s", project)
    else:
        logger.info("LangSmith tracing disabled — no API key set. Set LANGCHAIN_API_KEY to enable.")


# ---------------------------------------------------------------------------
# OpenTelemetry setup
# ---------------------------------------------------------------------------

_OTEL_AVAILABLE = False
_otel_tracer = None
_otel_meter = None

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource
    _OTEL_AVAILABLE = True
except ImportError:
    pass


def configure_opentelemetry(
    service_name: str = "cloud-optimizer-agents",
    enable_console_export: bool = False,
):
    """
    Configure OpenTelemetry tracing and metrics.

    In production, replace ConsoleExporters with OTLPSpanExporter /
    OTLPMetricExporter pointing at your collector.
    """
    global _otel_tracer, _otel_meter

    if not _OTEL_AVAILABLE:
        logger.info("OpenTelemetry SDK not installed — infrastructure metrics disabled")
        return

    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)
    if enable_console_export:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    # Check for OTLP exporter
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
            logger.info("OpenTelemetry OTLP exporter configured — endpoint: %s", otlp_endpoint)
    except ImportError:
        pass

    trace.set_tracer_provider(provider)
    _otel_tracer = trace.get_tracer("agent.orchestrator")

    reader = PeriodicExportingMetricReader(
        ConsoleMetricExporter() if enable_console_export else ConsoleMetricExporter(),
        export_interval_millis=60000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)
    _otel_meter = metrics.get_meter("agent.metrics")

    logger.info("OpenTelemetry configured — service: %s", service_name)


# ---------------------------------------------------------------------------
# Built-in trace collector (always available, no external deps)
# ---------------------------------------------------------------------------

@dataclass
class SpanRecord:
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
    Built-in trace collector. Works without any external infrastructure.

    Stores spans and metrics in memory for the WebSocket API to stream
    to the frontend. When OTel is configured, spans are also exported
    to the configured backend.
    """

    def __init__(self):
        self._spans: Dict[str, List[SpanRecord]] = {}
        self._metrics: List[MetricRecord] = []
        self._listeners: List[Callable] = []

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

        # Also create OTel span if available
        otel_span = None
        if _otel_tracer:
            otel_span = _otel_tracer.start_span(operation, attributes=attributes or {})

        try:
            yield record
        except Exception as e:
            record.status = "error"
            record.events.append({
                "name": "exception",
                "attributes": {"exception.message": str(e)},
                "timestamp": time.time(),
            })
            if otel_span:
                otel_span.set_status(trace.StatusCode.ERROR, str(e))
            raise
        finally:
            record.end_time = time.time()
            self._spans.setdefault(trace_id, []).append(record)
            self._notify("span_end", record.to_dict())
            if otel_span:
                otel_span.end()

    def record_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        record = MetricRecord(name=name, value=value, labels=labels or {})
        self._metrics.append(record)
        self._notify("metric", record.to_dict())

    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._spans.get(trace_id, [])]

    def get_all_traces(self) -> Dict[str, List[Dict[str, Any]]]:
        return {tid: [s.to_dict() for s in spans] for tid, spans in self._spans.items()}

    def get_metrics(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._metrics[-limit:]]

    def get_session_summary(self, trace_id: str) -> Dict[str, Any]:
        spans = self._spans.get(trace_id, [])
        if not spans:
            return {}

        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "agents_involved": list({s.agent for s in spans}),
            "total_duration_ms": round(sum(s.duration_ms for s in spans), 2),
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
