"""
Multi-agent cloud optimization framework powered by LangGraph.

Architecture:
  - graph.py       : LangGraph StateGraph definition and compilation
  - nodes.py       : Graph node functions (specialist agents, critique, verify, etc.)
  - state.py       : TypedDict state flowing through the graph
  - orchestrator.py: Public API wrapping the compiled graph
  - guardrails.py  : Verification gates for recommendation quality
  - context.py     : Signal domain filtering per agent
  - memory.py      : Three-tier memory (working / short-term / long-term)
  - evaluation.py  : Quality metrics and benchmarking
  - observability.py: LangSmith + OpenTelemetry integration
  - session.py     : Session lifecycle and handoff
"""
