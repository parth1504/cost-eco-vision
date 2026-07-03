"""
Typed structures shared across the S3 intelligence pipeline.

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

    #
    # S3-specific optimization level
    #
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
    """
    Time-aligned series of (timestamp, value) pairs.
    """

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
    Everything the S3 intelligence agent
    sees for one bucket.
    """

    #
    # Identity
    #
    bucket_name: str

    bucket_id: str = ""

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
    # Storage telemetry
    #
    total_storage_bytes: Optional[
        MetricSeries
    ] = None

    object_count: Optional[
        MetricSeries
    ] = None

    storage_growth_rate: Optional[
        MetricSeries
    ] = None

    small_object_ratio: Optional[
        MetricSeries
    ] = None

    stale_object_ratio: Optional[
        MetricSeries
    ] = None

    #
    # Access telemetry
    #
    get_requests: Optional[
        MetricSeries
    ] = None

    put_requests: Optional[
        MetricSeries
    ] = None

    retrieval_rate: Optional[
        MetricSeries
    ] = None

    data_transfer_out: Optional[
        MetricSeries
    ] = None

    access_spikes: Optional[
        MetricSeries
    ] = None

    #
    # Lifecycle + tiering
    #
    glacier_transition_rate: Optional[
        MetricSeries
    ] = None

    intelligent_tiering_ratio: Optional[
        MetricSeries
    ] = None

    lifecycle_transition_failures: Optional[
        MetricSeries
    ] = None

    #
    # Replication + durability
    #
    replication_latency: Optional[
        MetricSeries
    ] = None

    replication_failures: Optional[
        MetricSeries
    ] = None

    #
    # Cost telemetry
    #
    storage_cost: Optional[
        MetricSeries
    ] = None

    retrieval_cost: Optional[
        MetricSeries
    ] = None

    transfer_cost: Optional[
        MetricSeries
    ] = None

    #
    # Security posture
    #
    public_access_enabled: Optional[
        bool
    ] = None

    encryption_enabled: Optional[
        bool
    ] = None

    kms_enabled: Optional[
        bool
    ] = None

    versioning_enabled: Optional[
        bool
    ] = None

    mfa_delete_enabled: Optional[
        bool
    ] = None

    access_logging_enabled: Optional[
        bool
    ] = None

    replication_enabled: Optional[
        bool
    ] = None

    lifecycle_enabled: Optional[
        bool
    ] = None

    object_lock_enabled: Optional[
        bool
    ] = None

    bucket_policy: Dict[str, Any] = field(
        default_factory=dict
    )

    acl: Dict[str, Any] = field(
        default_factory=dict
    )

    #
    # Operational telemetry
    #
    events: List[Dict[str, Any]] = field(
        default_factory=list
    )

    audit_findings: Dict[str, Any] = field(
        default_factory=dict
    )

    access_patterns: Dict[str, Any] = field(
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
    """
    Discrete intelligence observation derived from telemetry.
    """

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
    # Operational metadata
    #
    impact: str = "medium"

    blast_radius: str = "bucket"

    operational_risk: str = "low"

    rollback: str = ""

    #
    # Financial
    #
    estimated_savings: Any = "N/A"

    cost_basis: str = ""

    #
    # S3-specific operational context
    #
    retrieval_impact: str = ""

    durability_impact: str = ""

    #
    # Remediation
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