"""
EC2 intelligence agent — production-grade infrastructure reasoning.

Now orchestrated via the unified LangGraph pipeline.
The legacy complex_orchestrator is preserved for backward compatibility
but is no longer the primary entry point.
"""


def run_complex_agent(*args, **kwargs):
    from agent.ec2_agent.complex_orchestrator import run_complex_agent as _run
    return _run(*args, **kwargs)


__all__ = ["run_complex_agent"]
