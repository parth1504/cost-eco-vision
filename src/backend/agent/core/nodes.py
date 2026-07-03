"""
LangGraph node functions for the multi-agent cloud optimization system.

Each function is a graph node that receives the current AgentState,
performs its work, and returns a partial state update. LangGraph merges
the update into the running state automatically.

Nodes:
  - supervisor        : Decides which node to route to next
  - ec2_specialist    : Runs EC2 analysis via existing complex_orchestrator
  - s3_specialist     : Runs S3 analysis via existing s3_agent
  - dynamodb_specialist : Runs DynamoDB analysis via existing dynamodb_agent
  - aggregate         : Merges specialist findings into flat recommendation list
  - critique          : Reviews recommendations for quality issues
  - refine            : Applies critique feedback
  - correlate         : Cross-resource pattern detection
  - verify            : Verification gates
  - evaluate          : Quality metrics
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from agent.core.state import AgentState
from agent.core.guardrails import run_all_gates, verify_conversation_depth
from agent.core.context import build_correlation_context
from agent.core.evaluation import evaluation_engine
from agent.core.memory import agent_memory

logger = logging.getLogger(__name__)

MAX_REFINEMENT_ITERATIONS = 2


# ---------------------------------------------------------------------------
# Supervisor — decides the next node
# ---------------------------------------------------------------------------

def supervisor(state: AgentState) -> dict:
    """Examine state and decide which node to invoke next."""
    findings = state.get("findings", {})
    has_findings = any(bool(v) for v in findings.values())
    has_critique = bool(state.get("critique_results", {}).get("reviewed"))
    critique_issues = state.get("critique_results", {}).get("critique", [])
    has_correlations = "correlations" in state and state["correlations"] is not None
    has_verified = bool(state.get("recommendations"))
    iteration = state.get("iteration", 0)
    resources = state.get("resources", [])

    if not has_findings:
        return {
            "next_action": "dispatch",
            "decisions": [_decision("supervisor", "dispatch_specialists",
                                    f"Starting analysis of {len(resources)} resources")],
        }

    if not has_critique:
        return {
            "next_action": "critique",
            "decisions": [_decision("supervisor", "request_critique",
                                    "Findings ready — requesting quality review")],
        }

    if critique_issues and iteration < MAX_REFINEMENT_ITERATIONS:
        return {
            "next_action": "refine",
            "iteration": iteration + 1,
            "decisions": [_decision("supervisor", "request_refinement",
                                    f"Critique found {len(critique_issues)} issues — refining (iteration {iteration + 1})")],
        }

    if not has_correlations and len(resources) > 1:
        return {
            "next_action": "correlate",
            "decisions": [_decision("supervisor", "request_correlation",
                                    f"Checking cross-resource patterns across {len(resources)} resources")],
        }

    if not has_verified:
        return {
            "next_action": "verify",
            "decisions": [_decision("supervisor", "run_verification",
                                    "Running verification gates on recommendations")],
        }

    return {
        "next_action": "evaluate",
        "decisions": [_decision("supervisor", "run_evaluation",
                                "Final evaluation and quality metrics")],
    }


# ---------------------------------------------------------------------------
# Specialist agents — wrap existing per-service orchestrators
# ---------------------------------------------------------------------------

def ec2_specialist(state: AgentState) -> dict:
    """Run EC2 analysis via the central analyzer entry point."""
    return _run_specialist(state, "EC2", "ec2_specialist")


def s3_specialist(state: AgentState) -> dict:
    """Run S3 analysis via the central analyzer entry point."""
    return _run_specialist(state, "S3", "s3_specialist")


def dynamodb_specialist(state: AgentState) -> dict:
    """Run DynamoDB analysis via the central analyzer entry point."""
    return _run_specialist(state, "DynamoDB", "dynamodb_specialist")


def _run_specialist(state: AgentState, resource_type: str, agent_name: str) -> dict:
    from agent.analyzer_agent.main import generateRecommendations

    resources = [r for r in state.get("resources", []) if r.get("type") == resource_type]
    recs = []
    for resource in resources:
        start = time.time()
        try:
            result = generateRecommendations(resource)
            recs.extend(result)
        except Exception as e:
            logger.error("%s failed for %s: %s", agent_name, resource.get("resource_id"), e)
        elapsed = (time.time() - start) * 1000
        logger.info("%s processed %s in %.0fms — %d recs",
                    agent_name, resource.get("resource_id"), elapsed, len(recs))

    findings = dict(state.get("findings", {}))
    findings[agent_name] = recs
    return {
        "findings": findings,
        "messages": [_message(agent_name, "supervisor",
                              f"Analyzed {len(resources)} {resource_type} resources — {len(recs)} recommendations")],
    }


# ---------------------------------------------------------------------------
# Aggregate — merge findings into flat list
# ---------------------------------------------------------------------------

def aggregate(state: AgentState) -> dict:
    """Flatten all specialist findings into a single recommendation list."""
    findings = state.get("findings", {})
    all_recs = []
    for agent_id, recs in findings.items():
        all_recs.extend(recs)

    return {
        "all_recommendations": all_recs,
        "messages": [_message("aggregator", "supervisor",
                              f"Aggregated {len(all_recs)} recommendations from {len(findings)} specialists")],
    }


# ---------------------------------------------------------------------------
# Critique — quality review
# ---------------------------------------------------------------------------

def critique(state: AgentState) -> dict:
    """Review all recommendations for quality issues."""
    recommendations = state.get("all_recommendations", [])
    if not recommendations:
        return {
            "critique_results": {"reviewed": True, "critique": [], "summary": "No recommendations to review"},
            "messages": [_message("critique", "supervisor", "No recommendations to review")],
        }

    critiques = []
    seen_types: Dict[str, List[str]] = {}

    for rec in recommendations:
        rule_id = rec.get("rule_id", "unknown")
        issues = []

        if not rec.get("evidence") and not rec.get("supporting_signals"):
            issues.append({"type": "missing_evidence", "detail": "No supporting evidence or signals", "severity": "high"})

        confidence = rec.get("confidence", 0)
        if confidence < 0.5:
            issues.append({"type": "low_confidence", "detail": f"Confidence {confidence:.2f} below threshold", "severity": "medium"})

        rec_type = rec.get("type", "")
        if rec_type in seen_types:
            for other_id in seen_types[rec_type]:
                issues.append({"type": "potential_conflict", "detail": f"Multiple {rec_type} recs: {other_id} and {rule_id}", "severity": "low"})
        seen_types.setdefault(rec_type, []).append(rule_id)

        sev = (rec.get("severity") or "").lower()
        if sev in ("critical", "high"):
            if not rec.get("rollback"):
                issues.append({"type": "missing_rollback", "detail": "High-severity rec without rollback plan", "severity": "medium"})
            if not rec.get("solution_steps"):
                issues.append({"type": "missing_steps", "detail": "High-severity rec without actionable steps", "severity": "medium"})

        if issues:
            critiques.append({"rule_id": rule_id, "title": rec.get("title", ""), "issues": issues})

    return {
        "critique_results": {
            "reviewed": True,
            "critique": critiques,
            "summary": f"Reviewed {len(recommendations)} recommendations, {len(critiques)} with issues",
        },
        "messages": [_message("critique", "supervisor",
                              f"Reviewed {len(recommendations)} recs — {len(critiques)} issues found")],
    }


# ---------------------------------------------------------------------------
# Refine — apply critique feedback
# ---------------------------------------------------------------------------

def refine(state: AgentState) -> dict:
    """Apply critique feedback to improve recommendations."""
    recommendations = list(state.get("all_recommendations", []))
    critique_data = state.get("critique_results", {})
    critiqued_rules = {c["rule_id"] for c in critique_data.get("critique", [])}

    refined_count = 0
    for rec in recommendations:
        rule_id = rec.get("rule_id", "")
        if rule_id not in critiqued_rules:
            continue

        issues = []
        for c in critique_data.get("critique", []):
            if c["rule_id"] == rule_id:
                issues = c.get("issues", [])
                break

        for issue in issues:
            issue_type = issue.get("type", "")
            if issue_type == "low_confidence":
                rec["confidence"] = max(0, rec.get("confidence", 0) - 0.1)
                refined_count += 1
            elif issue_type == "missing_rollback":
                rec["rollback"] = rec.get("rollback") or "Reverse the applied action manually."
                refined_count += 1
            elif issue_type == "missing_evidence":
                rec["confidence"] = max(0, rec.get("confidence", 0) - 0.15)
                refined_count += 1

    return {
        "all_recommendations": recommendations,
        "critique_results": {"reviewed": True, "critique": [], "summary": "Refinement applied"},
        "decisions": [_decision("refine", "apply_critique_feedback",
                                f"Refined {refined_count} recommendations based on critique")],
        "messages": [_message("refine", "supervisor", f"Applied {refined_count} refinements")],
    }


# ---------------------------------------------------------------------------
# Correlate — cross-resource patterns
# ---------------------------------------------------------------------------

def correlate(state: AgentState) -> dict:
    """Find cross-resource patterns and compound optimization opportunities."""
    findings = state.get("findings", {})
    resources = state.get("resources", [])
    all_recs = state.get("all_recommendations", [])

    correlations = []

    idle_recs = [r for r in all_recs if "idle" in (r.get("title") or "").lower()]
    if len(idle_recs) >= 2:
        total_savings = sum(
            float(r.get("saving", 0) or r.get("estimated_savings", 0) or 0)
            for r in idle_recs
            if isinstance(r.get("saving", r.get("estimated_savings")), (int, float))
        )
        correlations.append({
            "type": "compound_savings",
            "title": "Multiple idle resources — combined savings opportunity",
            "description": f"{len(idle_recs)} idle resources detected across services",
            "combined_savings": total_savings,
            "confidence": 0.85,
        })

    security_recs = [r for r in all_recs if r.get("type") == "security"]
    title_counts: Dict[str, int] = {}
    for r in security_recs:
        title = r.get("title", "")
        title_counts[title] = title_counts.get(title, 0) + 1
    for title, count in title_counts.items():
        if count >= 2:
            correlations.append({
                "type": "security_pattern",
                "title": f"Recurring security gap: {title}",
                "description": f"{count} resources share the same security issue",
                "confidence": 0.9,
            })

    by_service: Dict[str, List[str]] = {}
    for r in resources:
        svc = (r.get("tags") or {}).get("Service", "")
        if svc:
            by_service.setdefault(svc, []).append(r.get("resource_id", ""))
    for svc, rids in by_service.items():
        if len(rids) >= 2:
            svc_recs = [r for r in all_recs if r.get("resource_id") in rids]
            if svc_recs:
                correlations.append({
                    "type": "service_dependency",
                    "title": f"Co-located resources in service '{svc}'",
                    "description": f"{len(rids)} resources tagged to same service",
                    "resources_involved": rids,
                    "recommendation_count": len(svc_recs),
                    "confidence": 0.7,
                })

    return {
        "correlations": correlations,
        "messages": [_message("correlation", "supervisor",
                              f"Found {len(correlations)} cross-resource patterns")],
        "decisions": [_decision("correlation", "cross_resource_analysis",
                                f"Detected {len(correlations)} patterns across {len(resources)} resources")],
    }


# ---------------------------------------------------------------------------
# Verify — verification gates
# ---------------------------------------------------------------------------

def verify(state: AgentState) -> dict:
    """Run verification gates on all recommendations."""
    all_recs = state.get("all_recommendations", [])
    messages = state.get("messages", [])

    gates = []
    depth_gate = verify_conversation_depth(len(messages))
    gates.append(depth_gate.to_dict())

    verified = []
    dropped = 0
    for rec in all_recs:
        rec_gates = run_all_gates(rec)
        for g in rec_gates:
            gates.append(g.to_dict())

        from agent.core.types import VerificationResult
        failed = any(g.result == VerificationResult.FAILED for g in rec_gates)
        if not failed:
            rec["verification"] = {
                "gates_passed": sum(1 for g in rec_gates if g.result == VerificationResult.PASSED),
                "gates_review": sum(1 for g in rec_gates if g.result == VerificationResult.NEEDS_REVIEW),
                "verified_at": time.time(),
            }
            verified.append(rec)
        else:
            dropped += 1
            logger.info("Recommendation %s dropped by verification gate", rec.get("rule_id", "unknown"))

    return {
        "recommendations": verified,
        "verification_gates": gates,
        "decisions": [_decision("verify", "verification_gates",
                                f"Verified {len(verified)}/{len(all_recs)} passed, {dropped} dropped")],
        "messages": [_message("verify", "supervisor",
                              f"{len(verified)} recommendations passed verification")],
    }


# ---------------------------------------------------------------------------
# Evaluate — quality metrics
# ---------------------------------------------------------------------------

def evaluate(state: AgentState) -> dict:
    """Run evaluation metrics on verified recommendations."""
    recommendations = state.get("recommendations", [])
    resources = state.get("resources", [])

    for resource in resources:
        resource_recs = [
            r for r in recommendations
            if r.get("resource_id") == resource.get("resource_id") or not r.get("resource_id")
        ]
        if resource_recs:
            evaluation_engine.evaluate_recommendations(resource_recs, [], resource)

    session_id = state.get("session_id", "")
    agent_memory.store_session_state(session_id, {
        "session_id": session_id,
        "status": "completed",
        "recommendation_count": len(recommendations),
        "resource_count": len(resources),
    })
    agent_memory.store_session_snapshot(session_id, {
        "session_id": session_id,
        "recommendation_count": len(recommendations),
        "status": "completed",
        "resource_count": len(resources),
    })

    return {
        "status": "completed",
        "next_action": "__end__",
        "decisions": [_decision("evaluate", "quality_metrics",
                                f"Evaluated {len(recommendations)} recommendations across {len(resources)} resources")],
        "messages": [_message("evaluate", "supervisor",
                              f"Evaluation complete — {len(recommendations)} final recommendations")],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision(agent: str, action: str, reasoning: str) -> Dict[str, Any]:
    return {
        "agent": agent,
        "action": action,
        "reasoning": reasoning,
        "timestamp": time.time(),
    }


def _message(from_agent: str, to_agent: str, content: str) -> Dict[str, Any]:
    return {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "content": content,
        "timestamp": time.time(),
    }
