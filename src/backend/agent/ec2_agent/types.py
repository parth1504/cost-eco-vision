"""
Typed structures shared across the SRE agent pipeline.

We model everything as dataclasses (not dicts) inside the agent so the
contract between layers is explicit. At the orchestrator boundary we
serialize to dicts for compatibility with the existing recommendations
shape consumed by the frontend.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


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
# Telemetry — everything we know about an instance
# ---------------------------------------------------------------------------

@dataclass
class MetricSeries:
    """
    Time-aligned series of (timestamp, value) pairs.

    When summary stats are KNOWN (e.g. CloudWatch returned avg_7d / max_7d
    directly without raw points), the caller can pass `explicit_avg` /
    `explicit_max` so the properties return the real numbers instead of
    a degenerate computed-from-2-points value.
    """
    name: str
    points: List[tuple] = field(default_factory=list)  # [(datetime, float), ...]
    unit: str = ""
    explicit_avg: Optional[float] = None
    explicit_max: Optional[float] = None
    explicit_min: Optional[float] = None

    @property
    def values(self) -> List[float]:
        return [v for _, v in self.points]

    @property
    def avg(self) -> Optional[float]:
        if self.explicit_avg is not None:
            return self.explicit_avg
        v = self.values
        return sum(v) / len(v) if v else None

    @property
    def max(self) -> Optional[float]:
        if self.explicit_max is not None:
            return self.explicit_max
        v = self.values
        return max(v) if v else None

    @property
    def min(self) -> Optional[float]:
        if self.explicit_min is not None:
            return self.explicit_min
        v = self.values
        return min(v) if v else None


@dataclass
class TelemetryBundle:
    """Everything the agent gets to see for one instance."""
    # Identity
    instance_id: str
    instance_type: str = ""
    region: str = ""
    state: str = ""
    launch_time: Optional[datetime] = None
    tags: Dict[str, str] = field(default_factory=dict)

    # Cost
    monthly_cost: float = 0.0
    is_spot: bool = False
    is_reserved: bool = False

    # Metrics (filled by collector)
    cpu: Optional[MetricSeries] = None
    memory: Optional[MetricSeries] = None
    swap: Optional[MetricSeries] = None
    disk_used_pct: Optional[MetricSeries] = None
    disk_read_iops: Optional[MetricSeries] = None
    disk_write_iops: Optional[MetricSeries] = None
    ebs_burst_balance: Optional[MetricSeries] = None
    network_in: Optional[MetricSeries] = None
    network_out: Optional[MetricSeries] = None
    packet_drops: Optional[MetricSeries] = None
    tcp_connections: Optional[MetricSeries] = None
    process_count: Optional[MetricSeries] = None
    status_check_failed: Optional[MetricSeries] = None
    reboot_count_7d: int = 0

    # Operational events (deployments, scaling, AMI updates)
    events: List[Dict[str, Any]] = field(default_factory=list)

    # Logs (mocked / real OOM, GC, timeout signals)
    log_signals: Dict[str, int] = field(default_factory=dict)

    # APM (optional)
    p95_latency: Optional[MetricSeries] = None
    p99_latency: Optional[MetricSeries] = None

    # Config (security-relevant)
    imdsv2_required: Optional[bool] = None
    ebs_encrypted: Optional[bool] = None
    public_ip: Optional[str] = None
    open_ports_world: List[int] = field(default_factory=list)
    ami_age_days: Optional[int] = None

    # Reliability
    autoscaling_attached: Optional[bool] = None
    autoscaling_az_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Signals — discrete findings extracted from telemetry
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """
    A discrete observation about the instance, derived from raw telemetry.
    Signals are what the rule engine and LLM reasoning consume — never
    raw metric arrays.
    """
    name: str                          # canonical id e.g. "cpu_sustained_high"
    description: str = ""              # human-readable
    severity: Severity = Severity.INFO
    confidence: float = 0.7            # 0..1
    evidence: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Recommendation — the final actionable output
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    rule_id: str                       # stable id used for dedup
    title: str
    type: RecType
    category: RecCategory
    severity: Severity
    confidence: float                  # 0..1
    description: str
    issue: str                         # one-line problem statement

    # Causality / explanation
    reasoning: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    supporting_signals: List[str] = field(default_factory=list)

    # Operational impact
    impact: str = "medium"             # low / medium / high
    blast_radius: str = "instance"     # instance / service / account
    operational_risk: str = "low"      # low / medium / high
    rollback: str = ""                 # how to undo

    # Cost
    estimated_savings: Any = "N/A"
    cost_basis: str = ""

    # Actions
    solution_steps: List[Dict[str, Any]] = field(default_factory=list)
    boto3_sequence: List[Dict[str, Any]] = field(default_factory=list)
    manual_only: bool = False

    # Dedup / lifecycle
    status: str = "active"
    detected_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Coerce enums + datetimes for JSON / DDB compatibility.
        d["type"] = self.type.value
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["detected_at"] = self.detected_at.isoformat()
        return d
