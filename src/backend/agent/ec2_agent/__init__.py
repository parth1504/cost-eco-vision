"""
SRE Agent — production-grade EC2 infrastructure reasoning system.

Layered architecture (data flows top-down):

    Collector  →  Normalizer  →  Signals (features + anomalies)
        ↓
    Specialized agents (Metric, Cost, Reliability, Security, Root-Cause)
        ↓
    Safety / Guardrails  →  Ranker / Dedup  →  Memory
        ↓
    Human-readable Recommendations

Public entry point: `run_sre_agent(resource)`. Returns a list of
recommendations in the same shape as the legacy analyzer so it's a
drop-in replacement.
"""

from agent.ec2_agent.orchestrator import run_sre_agent

__all__ = ["run_sre_agent"]
