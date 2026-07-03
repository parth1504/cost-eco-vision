"""
Evaluation and benchmarking framework.

Measures the quality of agent recommendations across multiple dimensions:
  - Cost accuracy     : projected savings vs. actual (when adoption data exists)
  - Recommendation quality : signal coverage, evidence density, actionability
  - Agent performance : latency, token usage, error rate
  - Confidence calibration : are high-confidence recs actually correct?

Also provides a benchmark runner for regression testing — run a set of
known resources through the pipeline and compare output to golden baselines.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class EvalMetric:
    name: str
    value: float
    unit: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "unit": self.unit,
            "labels": self.labels,
            "timestamp": self.timestamp,
        }


@dataclass
class BenchmarkCase:
    name: str
    resource: Dict[str, Any]
    expected_rule_ids: List[str]
    expected_min_count: int = 1
    expected_max_count: int = 20
    must_not_contain: List[str] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    case_name: str
    passed: bool
    actual_rule_ids: List[str]
    missing_rules: List[str]
    unexpected_rules: List[str]
    recommendation_count: int
    duration_ms: float
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_name": self.case_name,
            "passed": self.passed,
            "actual_rule_ids": self.actual_rule_ids,
            "missing_rules": self.missing_rules,
            "unexpected_rules": self.unexpected_rules,
            "recommendation_count": self.recommendation_count,
            "duration_ms": round(self.duration_ms, 2),
            "details": self.details,
        }


class EvaluationEngine:
    """Collects and computes quality metrics across agent runs."""

    def __init__(self):
        self._metrics: List[EvalMetric] = []
        self._benchmark_results: List[BenchmarkResult] = []

    def evaluate_recommendations(
        self,
        recommendations: List[Dict[str, Any]],
        signals: List[Dict[str, Any]],
        resource: Dict[str, Any],
    ) -> List[EvalMetric]:
        """Score a set of recommendations on multiple quality dimensions."""
        metrics = []

        # Signal coverage: what fraction of detected signals are addressed
        signal_names = {s.get("name") for s in signals if s.get("name")}
        addressed = set()
        for rec in recommendations:
            for sig in rec.get("supporting_signals", []):
                addressed.add(sig)

        coverage = len(addressed) / len(signal_names) if signal_names else 0
        metrics.append(EvalMetric(
            name="signal_coverage",
            value=coverage,
            unit="ratio",
            labels={"resource_id": resource.get("resource_id", "")},
        ))

        # Evidence density: avg evidence items per recommendation
        if recommendations:
            evidence_counts = [len(r.get("evidence", {})) for r in recommendations]
            avg_evidence = sum(evidence_counts) / len(evidence_counts)
        else:
            avg_evidence = 0
        metrics.append(EvalMetric(
            name="evidence_density",
            value=avg_evidence,
            unit="items",
            labels={"resource_id": resource.get("resource_id", "")},
        ))

        # Actionability: fraction of recs with solution_steps
        if recommendations:
            actionable = sum(1 for r in recommendations if r.get("solution_steps"))
            actionability = actionable / len(recommendations)
        else:
            actionability = 0
        metrics.append(EvalMetric(
            name="actionability",
            value=actionability,
            unit="ratio",
            labels={"resource_id": resource.get("resource_id", "")},
        ))

        # Confidence distribution
        if recommendations:
            confs = [r.get("confidence", 0) for r in recommendations]
            metrics.append(EvalMetric(
                name="avg_confidence",
                value=sum(confs) / len(confs),
                unit="score",
            ))
            metrics.append(EvalMetric(
                name="min_confidence",
                value=min(confs),
                unit="score",
            ))

        # Severity distribution
        severity_counts: Dict[str, int] = {}
        for rec in recommendations:
            sev = rec.get("severity", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        for sev, count in severity_counts.items():
            metrics.append(EvalMetric(
                name="severity_count",
                value=count,
                unit="count",
                labels={"severity": sev},
            ))

        self._metrics.extend(metrics)
        return metrics

    def evaluate_cost_accuracy(
        self,
        projected_savings: float,
        actual_savings: float,
    ) -> EvalMetric:
        """Compare projected vs actual savings."""
        if projected_savings == 0:
            accuracy = 1.0 if actual_savings == 0 else 0.0
        else:
            accuracy = 1.0 - abs(projected_savings - actual_savings) / projected_savings

        metric = EvalMetric(
            name="cost_accuracy",
            value=max(0, accuracy),
            unit="ratio",
            labels={
                "projected": str(projected_savings),
                "actual": str(actual_savings),
            },
        )
        self._metrics.append(metric)
        return metric

    def run_benchmark(
        self,
        cases: List[BenchmarkCase],
        agent_fn: Callable,
    ) -> List[BenchmarkResult]:
        """Run benchmark cases through the agent and compare to expected output."""
        results = []

        for case in cases:
            start = time.time()
            try:
                recs = agent_fn(case.resource)
            except Exception as e:
                results.append(BenchmarkResult(
                    case_name=case.name,
                    passed=False,
                    actual_rule_ids=[],
                    missing_rules=case.expected_rule_ids,
                    unexpected_rules=[],
                    recommendation_count=0,
                    duration_ms=(time.time() - start) * 1000,
                    details=f"Agent raised: {e}",
                ))
                continue

            elapsed = (time.time() - start) * 1000
            actual_ids = [r.get("rule_id", "") for r in recs]
            actual_set = set(actual_ids)
            expected_set = set(case.expected_rule_ids)

            missing = list(expected_set - actual_set)
            unexpected = [r for r in actual_ids if r in case.must_not_contain]

            passed = (
                not missing
                and not unexpected
                and case.expected_min_count <= len(recs) <= case.expected_max_count
            )

            result = BenchmarkResult(
                case_name=case.name,
                passed=passed,
                actual_rule_ids=actual_ids,
                missing_rules=missing,
                unexpected_rules=unexpected,
                recommendation_count=len(recs),
                duration_ms=elapsed,
            )
            results.append(result)

        self._benchmark_results.extend(results)
        return results

    def get_metrics(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._metrics[-limit:]]

    def get_benchmark_results(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._benchmark_results]

    def get_summary(self) -> Dict[str, Any]:
        if not self._metrics:
            return {"total_metrics": 0}

        by_name: Dict[str, List[float]] = {}
        for m in self._metrics:
            by_name.setdefault(m.name, []).append(m.value)

        averages = {
            name: round(sum(vals) / len(vals), 4)
            for name, vals in by_name.items()
        }

        benchmark_pass_rate = 0
        if self._benchmark_results:
            passed = sum(1 for r in self._benchmark_results if r.passed)
            benchmark_pass_rate = round(passed / len(self._benchmark_results), 3)

        return {
            "total_metrics": len(self._metrics),
            "averages": averages,
            "benchmark_pass_rate": benchmark_pass_rate,
            "benchmark_count": len(self._benchmark_results),
        }


# Singleton
evaluation_engine = EvaluationEngine()
