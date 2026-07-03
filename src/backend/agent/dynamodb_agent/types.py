"""
Typed structures shared across the DynamoDB intelligence pipeline.

We model everything as dataclasses (not dicts) inside the agent so the
contract between layers is explicit.

At the orchestrator boundary we serialize to dicts for compatibility
with the existing frontend recommendation shape.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
    asdict,
)

from datetime import datetime

from enum import Enum

from typing import (
    Any,
    Dict,
    List,
    Optional,
)


# ---------------------------------------------------------------------------
# Severity, category, and status enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    WARNING = "warning"
    LOW = "low"
    INFO = "info"

    OPTIMIZATION = "optimization"


class RecCategory(str, Enum):

    CRITICAL = "Critical"
    WARNING = "Warning"
    OPTIMIZATION = "Optimization"
    INFORMATIONAL = "Informational"


class RecType(str, Enum):

    COST = "cost"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    SECURITY = "security"
    OPERATIONAL = "operational"


# ---------------------------------------------------------------------------
# MetricSeries
# ---------------------------------------------------------------------------

@dataclass
class MetricSeries:

    name: str

    points: List[tuple] = field(
        default_factory=list
    )

    unit: str = ""

    explicit_avg: Optional[float] = None
    explicit_max: Optional[float] = None
    explicit_min: Optional[float] = None

    @property
    def values(self) -> List[float]:

        return [
            v for _, v in self.points
        ]

    @property
    def avg(self) -> Optional[float]:

        if self.explicit_avg is not None:
            return self.explicit_avg

        vals = self.values

        return (
            sum(vals) / len(vals)
            if vals else None
        )

    @property
    def max(self) -> Optional[float]:

        if self.explicit_max is not None:
            return self.explicit_max

        vals = self.values

        return max(vals) if vals else None

    @property
    def min(self) -> Optional[float]:

        if self.explicit_min is not None:
            return self.explicit_min

        vals = self.values

        return min(vals) if vals else None


# ---------------------------------------------------------------------------
# Telemetry Bundle
# ---------------------------------------------------------------------------

@dataclass
class TelemetryBundle:
    """
    Everything the DynamoDB intelligence
    agent sees for one table.
    """

    #
    # Identity
    #
    table_name: str

    table_id: str = ""

    region: str = ""

    state: str = ""

    creation_time: Optional[datetime] = None

    tags: Dict[str, str] = field(
        default_factory=dict
    )

    #
    # Financial
    #
    monthly_cost: float = 0.0

    #
    # Capacity telemetry
    #
    consumed_rcu: Optional[
        MetricSeries
    ] = None

    provisioned_rcu: Optional[
        MetricSeries
    ] = None

    consumed_wcu: Optional[
        MetricSeries
    ] = None

    provisioned_wcu: Optional[
        MetricSeries
    ] = None

    rcu_utilization: Optional[
        MetricSeries
    ] = None

    wcu_utilization: Optional[
        MetricSeries
    ] = None

    burst_capacity_usage: Optional[
        MetricSeries
    ] = None

    #
    # Performance telemetry
    #
    throttled_requests: Optional[
        MetricSeries
    ] = None

    retry_rate: Optional[
        MetricSeries
    ] = None

    timeout_rate: Optional[
        MetricSeries
    ] = None

    failed_requests: Optional[
        MetricSeries
    ] = None

    p95_latency: Optional[
        MetricSeries
    ] = None

    p99_latency: Optional[
        MetricSeries
    ] = None

    scan_frequency: Optional[
        MetricSeries
    ] = None

    #
    # Partition behavior
    #
    hot_partition_ratio: Optional[
        MetricSeries
    ] = None

    partition_skew_ratio: Optional[
        MetricSeries
    ] = None

    adaptive_capacity_usage: Optional[
        MetricSeries
    ] = None

    #
    # Cost telemetry
    #
    read_cost: Optional[
        MetricSeries
    ] = None

    write_cost: Optional[
        MetricSeries
    ] = None

    storage_cost: Optional[
        MetricSeries
    ] = None

    backup_cost: Optional[
        MetricSeries
    ] = None

    gsi_cost: Optional[
        MetricSeries
    ] = None

    #
    # Reliability
    #
    replication_lag: Optional[
        MetricSeries
    ] = None

    autoscaling_flaps: Optional[
        MetricSeries
    ] = None

    #
    # Configuration
    #
    billing_mode: Optional[str] = None

    pitr_enabled: Optional[bool] = None

    streams_enabled: Optional[bool] = None

    autoscaling_enabled: Optional[
        bool
    ] = None

    global_table_enabled: Optional[
        bool
    ] = None

    encryption_enabled: Optional[
        bool
    ] = None

    kms_key: Optional[str] = None

    backup_enabled: Optional[
        bool
    ] = None

    table_class: Optional[str] = None

    gsis: List[Dict[str, Any]] = field(
        default_factory=list
    )

    partition_key: Optional[str] = None

    sort_key: Optional[str] = None

    #
    # Operational telemetry
    #
    events: List[Dict[str, Any]] = field(
        default_factory=list
    )

    log_signals: Dict[str, int] = field(
        default_factory=dict
    )

    workload_patterns: Dict[str, Any] = field(
        default_factory=dict
    )

    historical_trends: Dict[str, Any] = field(
        default_factory=dict
    )


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@dataclass
class Signal:

    name: str

    description: str = ""

    severity: Severity = Severity.INFO

    confidence: float = 0.7

    evidence: Dict[str, Any] = field(
        default_factory=dict
    )

    detected_at: datetime = field(
        default_factory=datetime.utcnow
    )


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:

    rule_id: str

    title: str

    type: RecType

    category: RecCategory

    severity: Severity

    confidence: float

    description: str

    issue: str

    #
    # Reasoning
    #
    reasoning: str = ""

    evidence: Dict[str, Any] = field(
        default_factory=dict
    )

    supporting_signals: List[str] = field(
        default_factory=list
    )

    #
    # Operational
    #
    impact: str = "medium"

    blast_radius: str = "table"

    operational_risk: str = "low"

    rollback: str = ""

    #
    # Financial
    #
    estimated_savings: Any = "N/A"

    cost_basis: str = ""

    #
    # DynamoDB-specific context
    #
    latency_impact: str = ""

    durability_impact: str = ""

    #
    # Actions
    #
    solution_steps: List[
        Dict[str, Any]
    ] = field(default_factory=list)

    boto3_sequence: List[
        Dict[str, Any]
    ] = field(default_factory=list)

    manual_only: bool = False

    #
    # Lifecycle
    #
    status: str = "active"

    detected_at: datetime = field(
        default_factory=datetime.utcnow
    )

    def to_dict(self) -> Dict[str, Any]:

        d = asdict(self)

        d["type"] = self.type.value

        d["category"] = self.category.value

        d["severity"] = self.severity.value

        d["detected_at"] = (
            self.detected_at.isoformat()
        )

        return d