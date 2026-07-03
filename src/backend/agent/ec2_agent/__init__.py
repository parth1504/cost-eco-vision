"""
EC2 intelligence agent — production-grade infrastructure reasoning.

Uses an LLM router (complex_orchestrator) to dynamically decide which
specialist agent (metric, cost, reliability, security, root-cause) to
invoke at each step based on signals and accumulated findings.
"""

from agent.ec2_agent.complex_orchestrator import run_complex_agent

__all__ = ["run_complex_agent"]
