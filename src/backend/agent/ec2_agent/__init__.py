"""
EC2 intelligence agent.

All analysis is orchestrated via the unified LangGraph pipeline
(agent.core.graph). Individual agent functions (metric_analyzer_agent,
cost_optimization_agent, etc.) are registered in register.py and
invoked dynamically by the pipeline's sub-agent nodes.
"""
