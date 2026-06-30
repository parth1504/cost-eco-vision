"""
Multi-agent orchestrator with free-form communication.

This is NOT a fixed pipeline. Agents can:
  - Talk to any other agent directly
  - Request critique of their findings
  - Ask the correlation agent to check cross-resource dependencies
  - Circle back for refinement based on feedback

The orchestrator's job is to:
  1. Initialize the session and agents
  2. Kick off the initial analysis
  3. Let agents communicate freely
  4. Run verification gates on the final output
  5. Stream everything to the UI via the trace collector
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from agent.core.types import (
    AgentDecision,
    AgentMessage,
    AgentRole,
    MessageType,
    SessionState,
    SessionStatus,
    VerificationResult,
)
from agent.core.registry import agent_registry, message_bus, AgentProtocol
from agent.core.memory import agent_memory
from agent.core.guardrails import run_all_gates, verify_conversation_depth
from agent.core.context import build_agent_context, build_critique_context, build_correlation_context
from agent.core.observability import trace_collector
from agent.core.evaluation import evaluation_engine

logger = logging.getLogger(__name__)


# ─── Specialist Agent Wrappers ──────────────────────────────────────────────
# These wrap the existing per-service orchestrators (ec2_agent, s3_agent,
# dynamodb_agent) into the AgentProtocol so they can participate in the mesh.

class EC2SpecialistAgent:
    agent_id = "ec2_specialist"
    capabilities = ["ec2_analysis", "cost_optimization", "performance", "reliability", "security"]

    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        from agent.ec2_agent.complex_orchestrator import run_complex_agent

        resource = message.payload.get("resource", {})
        if not resource or resource.get("type") != "EC2":
            return AgentMessage(
                from_agent=self.agent_id,
                to_agent=message.from_agent,
                message_type=MessageType.RESPONSE,
                payload={"recommendations": [], "note": "Not an EC2 resource"},
                reply_to=message.id,
            )

        with trace_collector.span(
            trace_id=message.trace_id,
            operation="ec2_specialist.analyze",
            agent=self.agent_id,
            attributes={"resource_id": resource.get("resource_id", "")},
        ) as span:
            recs = run_complex_agent(resource)
            span.attributes["recommendation_count"] = len(recs)

        return AgentMessage(
            from_agent=self.agent_id,
            to_agent=message.from_agent,
            message_type=MessageType.RESPONSE,
            payload={"recommendations": recs, "resource_id": resource.get("resource_id")},
            reply_to=message.id,
        )


class S3SpecialistAgent:
    agent_id = "s3_specialist"
    capabilities = ["s3_analysis", "cost_optimization", "security", "reliability"]

    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        from agent.s3_agent.orchestrator import run_s3_agent

        resource = message.payload.get("resource", {})
        if not resource or resource.get("type") != "S3":
            return AgentMessage(
                from_agent=self.agent_id,
                to_agent=message.from_agent,
                message_type=MessageType.RESPONSE,
                payload={"recommendations": [], "note": "Not an S3 resource"},
                reply_to=message.id,
            )

        with trace_collector.span(
            trace_id=message.trace_id,
            operation="s3_specialist.analyze",
            agent=self.agent_id,
            attributes={"resource_id": resource.get("resource_id", "")},
        ) as span:
            recs = run_s3_agent(resource)
            span.attributes["recommendation_count"] = len(recs)

        return AgentMessage(
            from_agent=self.agent_id,
            to_agent=message.from_agent,
            message_type=MessageType.RESPONSE,
            payload={"recommendations": recs, "resource_id": resource.get("resource_id")},
            reply_to=message.id,
        )


class DynamoDBSpecialistAgent:
    agent_id = "dynamodb_specialist"
    capabilities = ["dynamodb_analysis", "cost_optimization", "performance", "reliability"]

    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        from agent.dynamodb_agent.orchestrator import run_dynamodb_agent

        resource = message.payload.get("resource", {})
        if not resource or resource.get("type") != "DynamoDB":
            return AgentMessage(
                from_agent=self.agent_id,
                to_agent=message.from_agent,
                message_type=MessageType.RESPONSE,
                payload={"recommendations": [], "note": "Not a DynamoDB resource"},
                reply_to=message.id,
            )

        with trace_collector.span(
            trace_id=message.trace_id,
            operation="dynamodb_specialist.analyze",
            agent=self.agent_id,
            attributes={"resource_id": resource.get("resource_id", "")},
        ) as span:
            recs = run_dynamodb_agent(resource)
            span.attributes["recommendation_count"] = len(recs)

        return AgentMessage(
            from_agent=self.agent_id,
            to_agent=message.from_agent,
            message_type=MessageType.RESPONSE,
            payload={"recommendations": recs, "resource_id": resource.get("resource_id")},
            reply_to=message.id,
        )


class CritiqueAgent:
    """
    Reviews recommendations from other agents for quality issues:
    hallucinations, missing evidence, contradictions, safety gaps.
    """
    agent_id = "critique"
    capabilities = ["critique", "quality_review", "refinement"]

    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        recommendations = message.payload.get("recommendations", [])
        if not recommendations:
            return AgentMessage(
                from_agent=self.agent_id,
                to_agent=message.from_agent,
                message_type=MessageType.CRITIQUE_RESPONSE,
                payload={"critique": [], "summary": "No recommendations to review"},
                reply_to=message.id,
            )

        with trace_collector.span(
            trace_id=message.trace_id,
            operation="critique.review",
            agent=self.agent_id,
        ) as span:
            critiques = self._review(recommendations)
            span.attributes["critique_count"] = len(critiques)

        return AgentMessage(
            from_agent=self.agent_id,
            to_agent=message.from_agent,
            message_type=MessageType.CRITIQUE_RESPONSE,
            payload={
                "critique": critiques,
                "summary": f"Reviewed {len(recommendations)} recommendations, {len(critiques)} issues found",
            },
            reply_to=message.id,
        )

    def _review(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        critiques = []
        seen_types: Dict[str, List[str]] = {}

        for rec in recommendations:
            rule_id = rec.get("rule_id", "unknown")
            issues = []

            if not rec.get("evidence") and not rec.get("supporting_signals"):
                issues.append({
                    "type": "missing_evidence",
                    "detail": "No supporting evidence or signals cited",
                    "severity": "high",
                })

            confidence = rec.get("confidence", 0)
            if confidence < 0.5:
                issues.append({
                    "type": "low_confidence",
                    "detail": f"Confidence {confidence:.2f} is below quality threshold",
                    "severity": "medium",
                })

            rec_type = rec.get("type", "")
            if rec_type in seen_types:
                for other_id in seen_types[rec_type]:
                    issues.append({
                        "type": "potential_conflict",
                        "detail": f"Multiple {rec_type} recommendations: {other_id} and {rule_id}",
                        "severity": "low",
                    })
            seen_types.setdefault(rec_type, []).append(rule_id)

            sev = (rec.get("severity") or "").lower()
            if sev in ("critical", "high"):
                if not rec.get("rollback"):
                    issues.append({
                        "type": "missing_rollback",
                        "detail": f"High-severity rec without rollback plan",
                        "severity": "medium",
                    })
                if not rec.get("solution_steps"):
                    issues.append({
                        "type": "missing_steps",
                        "detail": "High-severity rec without actionable steps",
                        "severity": "medium",
                    })

            if issues:
                critiques.append({
                    "rule_id": rule_id,
                    "title": rec.get("title", ""),
                    "issues": issues,
                })

        return critiques


class CorrelationAgent:
    """
    Finds cross-resource patterns and compound optimization opportunities.
    """
    agent_id = "correlation"
    capabilities = ["correlation", "cross_resource_analysis", "dependency_detection"]

    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        findings = message.payload.get("findings_by_agent", {})
        resources = message.payload.get("resources", [])

        with trace_collector.span(
            trace_id=message.trace_id,
            operation="correlation.analyze",
            agent=self.agent_id,
        ) as span:
            correlations = self._find_correlations(findings, resources)
            span.attributes["correlation_count"] = len(correlations)

        return AgentMessage(
            from_agent=self.agent_id,
            to_agent=message.from_agent,
            message_type=MessageType.CORRELATION_RESPONSE,
            payload={"correlations": correlations},
            reply_to=message.id,
        )

    def _find_correlations(
        self,
        findings: Dict[str, List[Dict[str, Any]]],
        resources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        correlations = []

        # Gather all recs across agents
        all_recs: List[Dict[str, Any]] = []
        for agent_recs in findings.values():
            all_recs.extend(agent_recs)

        # Find compound savings: multiple idle/underutilized resources
        idle_recs = [r for r in all_recs if "idle" in (r.get("title") or "").lower()]
        if len(idle_recs) >= 2:
            total_savings = sum(
                float(r.get("saving", 0) or 0)
                for r in idle_recs
                if isinstance(r.get("saving"), (int, float))
            )
            correlations.append({
                "type": "compound_savings",
                "title": f"Multiple idle resources — combined savings opportunity",
                "description": f"{len(idle_recs)} idle resources detected across services",
                "resources_involved": [r.get("resource_id", "") for r in idle_recs if r.get("resource_id")],
                "combined_savings": total_savings,
                "confidence": 0.85,
            })

        # Find security patterns: multiple resources with same security gap
        security_recs = [r for r in all_recs if r.get("type") == "security"]
        security_titles: Dict[str, int] = {}
        for r in security_recs:
            title = r.get("title", "")
            security_titles[title] = security_titles.get(title, 0) + 1

        for title, count in security_titles.items():
            if count >= 2:
                correlations.append({
                    "type": "security_pattern",
                    "title": f"Recurring security gap: {title}",
                    "description": f"{count} resources share the same security issue",
                    "confidence": 0.9,
                })

        # Find resource dependencies via tags
        by_service_tag: Dict[str, List[str]] = {}
        for r in resources:
            svc = (r.get("tags") or {}).get("Service", "")
            if svc:
                by_service_tag.setdefault(svc, []).append(r.get("resource_id", ""))

        for svc, rids in by_service_tag.items():
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

        return correlations


# ─── Main Orchestrator ──────────────────────────────────────────────────────

class MultiAgentOrchestrator:
    """
    Runs a complete multi-agent optimization session.

    Flow:
      1. Dispatch resources to specialist agents (parallel by type)
      2. Agents communicate freely during analysis
      3. Critique agent reviews all findings
      4. Correlation agent checks cross-resource patterns
      5. Refinement loop if critique found issues
      6. Verification gates on final output
      7. Everything streamed via trace collector
    """

    def __init__(self):
        self._ensure_agents_registered()

    def _ensure_agents_registered(self):
        for agent_cls in [
            EC2SpecialistAgent,
            S3SpecialistAgent,
            DynamoDBSpecialistAgent,
            CritiqueAgent,
            CorrelationAgent,
        ]:
            if not agent_registry.get(agent_cls.agent_id):
                agent_registry.register(agent_cls())

    def run(self, resources: List[Dict[str, Any]], session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Run the full multi-agent analysis pipeline.
        Returns session state with all recommendations, decisions, traces.
        """
        session = SessionState(
            session_id=session_id or str(uuid.uuid4()),
            resources=resources,
        )

        # Check for prior session handoff
        prior = agent_memory.get_session_state(session.session_id)
        if prior:
            session.context["resumed_from"] = prior
            session.parent_session_id = prior.get("session_id")

        with trace_collector.span(
            trace_id=session.trace_id,
            operation="orchestrator.run",
            agent="orchestrator",
            attributes={"resource_count": len(resources), "session_id": session.session_id},
        ):
            try:
                # Phase 1: Dispatch to specialists
                all_findings = self._dispatch_to_specialists(session, resources)

                # Phase 2: Critique review
                all_recs = []
                for recs in all_findings.values():
                    all_recs.extend(recs)

                if all_recs:
                    critique_results = self._run_critique(session, all_recs)
                    session.context["critique"] = critique_results

                    # Phase 3: Refinement if critique found issues
                    if critique_results.get("critique"):
                        all_recs = self._refine(session, all_recs, critique_results)

                # Phase 4: Correlation analysis (if multiple resources)
                if len(resources) > 1:
                    correlations = self._run_correlation(session, all_findings, resources)
                    session.context["correlations"] = correlations

                # Phase 5: Verification gates
                verified_recs = self._verify_all(session, all_recs)

                # Phase 6: Evaluation
                self._evaluate(session, verified_recs, resources)

                session.recommendations = verified_recs
                session.status = SessionStatus.COMPLETED

            except Exception as e:
                logger.error("Orchestrator failed: %s", e, exc_info=True)
                session.status = SessionStatus.FAILED
                session.metadata["error"] = str(e)

            from datetime import datetime
            session.completed_at = datetime.utcnow()

        # Persist session
        agent_memory.store_session_state(session.session_id, session.to_dict())
        agent_memory.store_session_snapshot(session.session_id, {
            "session_id": session.session_id,
            "recommendation_count": len(session.recommendations),
            "status": session.status.value,
            "resource_count": len(resources),
        })

        return self._build_response(session)

    def _dispatch_to_specialists(
        self,
        session: SessionState,
        resources: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Send each resource to the appropriate specialist agent."""
        findings: Dict[str, List[Dict[str, Any]]] = {}
        agent_map = {
            "EC2": "ec2_specialist",
            "S3": "s3_specialist",
            "DynamoDB": "dynamodb_specialist",
        }

        for resource in resources:
            rtype = resource.get("type", "")
            agent_id = agent_map.get(rtype)
            if not agent_id:
                logger.warning("No specialist for resource type: %s", rtype)
                continue

            msg = AgentMessage(
                from_agent="orchestrator",
                to_agent=agent_id,
                message_type=MessageType.REQUEST,
                payload={"resource": resource},
                trace_id=session.trace_id,
            )

            session.decisions.append(AgentDecision(
                agent="orchestrator",
                action=f"dispatch_to_{agent_id}",
                reasoning=f"Resource type {rtype} maps to {agent_id}",
                inputs={"resource_id": resource.get("resource_id", ""), "type": rtype},
            ))

            start = time.time()
            response = message_bus.send(msg)
            elapsed = (time.time() - start) * 1000

            session.messages.append(msg)
            if response:
                session.messages.append(response)
                recs = response.payload.get("recommendations", [])
                findings.setdefault(agent_id, []).extend(recs)

                trace_collector.record_metric(
                    "agent.analysis_duration_ms",
                    elapsed,
                    labels={"agent": agent_id, "resource_type": rtype},
                )

        return findings

    def _run_critique(
        self,
        session: SessionState,
        recommendations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Ask the critique agent to review all recommendations."""
        msg = AgentMessage(
            from_agent="orchestrator",
            to_agent="critique",
            message_type=MessageType.CRITIQUE_REQUEST,
            payload={"recommendations": recommendations},
            trace_id=session.trace_id,
        )

        session.decisions.append(AgentDecision(
            agent="orchestrator",
            action="request_critique",
            reasoning=f"Requesting quality review of {len(recommendations)} recommendations",
            inputs={"recommendation_count": len(recommendations)},
        ))

        session.messages.append(msg)
        response = message_bus.send(msg)

        if response:
            session.messages.append(response)
            return response.payload

        return {"critique": [], "summary": "Critique agent unavailable"}

    def _refine(
        self,
        session: SessionState,
        recommendations: List[Dict[str, Any]],
        critique: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Apply critique feedback to refine recommendations."""
        critiqued_rules = {c["rule_id"] for c in critique.get("critique", [])}
        refined = []

        for rec in recommendations:
            rule_id = rec.get("rule_id", "")
            if rule_id not in critiqued_rules:
                refined.append(rec)
                continue

            issues = []
            for c in critique.get("critique", []):
                if c["rule_id"] == rule_id:
                    issues = c.get("issues", [])
                    break

            for issue in issues:
                issue_type = issue.get("type", "")
                if issue_type == "low_confidence":
                    rec["confidence"] = max(0, rec.get("confidence", 0) - 0.1)
                    rec["_refined"] = True
                elif issue_type == "missing_rollback":
                    rec["rollback"] = rec.get("rollback") or "Reverse the applied action manually."
                    rec["_refined"] = True
                elif issue_type == "missing_evidence":
                    rec["confidence"] = max(0, rec.get("confidence", 0) - 0.15)
                    rec["_refined"] = True

            refined.append(rec)

        session.decisions.append(AgentDecision(
            agent="orchestrator",
            action="refine_recommendations",
            reasoning=f"Applied critique to {len(critiqued_rules)} recommendations",
            outputs={"refined_count": sum(1 for r in refined if r.get("_refined"))},
        ))

        return refined

    def _run_correlation(
        self,
        session: SessionState,
        findings: Dict[str, List[Dict[str, Any]]],
        resources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Ask the correlation agent to find cross-resource patterns."""
        context = build_correlation_context(findings, resources)

        msg = AgentMessage(
            from_agent="orchestrator",
            to_agent="correlation",
            message_type=MessageType.CORRELATION_REQUEST,
            payload=context,
            trace_id=session.trace_id,
        )

        session.messages.append(msg)
        response = message_bus.send(msg)

        if response:
            session.messages.append(response)
            correlations = response.payload.get("correlations", [])

            session.decisions.append(AgentDecision(
                agent="orchestrator",
                action="correlation_analysis",
                reasoning=f"Found {len(correlations)} cross-resource patterns",
                outputs={"correlations": correlations},
            ))

            return correlations

        return []

    def _verify_all(
        self,
        session: SessionState,
        recommendations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Run verification gates on all recommendations."""
        depth_gate = verify_conversation_depth(len(session.messages))
        session.verification_gates.append(depth_gate)

        verified = []
        for rec in recommendations:
            gates = run_all_gates(rec)
            session.verification_gates.extend(gates)

            failed = any(g.result == VerificationResult.FAILED for g in gates)
            if not failed:
                rec["verification"] = {
                    "gates_passed": sum(1 for g in gates if g.result == VerificationResult.PASSED),
                    "gates_review": sum(1 for g in gates if g.result == VerificationResult.NEEDS_REVIEW),
                    "verified_at": time.time(),
                }
                verified.append(rec)
            else:
                logger.info(
                    "Recommendation %s dropped by verification gate",
                    rec.get("rule_id", "unknown"),
                )

        session.decisions.append(AgentDecision(
            agent="orchestrator",
            action="verification",
            reasoning=f"Verified {len(verified)}/{len(recommendations)} recommendations passed gates",
            outputs={
                "passed": len(verified),
                "dropped": len(recommendations) - len(verified),
            },
        ))

        return verified

    def _evaluate(
        self,
        session: SessionState,
        recommendations: List[Dict[str, Any]],
        resources: List[Dict[str, Any]],
    ):
        """Run evaluation metrics on the session output."""
        for resource in resources:
            resource_recs = [
                r for r in recommendations
                if r.get("resource_id") == resource.get("resource_id")
                or not r.get("resource_id")
            ]
            if resource_recs:
                evaluation_engine.evaluate_recommendations(
                    resource_recs, [], resource,
                )

    def _build_response(self, session: SessionState) -> Dict[str, Any]:
        """Build the final response payload."""
        return {
            "session": session.to_dict(),
            "recommendations": session.recommendations,
            "decisions": [d.to_dict() for d in session.decisions],
            "messages": [m.to_dict() for m in session.messages],
            "trace": trace_collector.get_trace(session.trace_id),
            "interaction_graph": message_bus.get_agent_interactions(session.trace_id),
            "verification_summary": {
                "total_gates": len(session.verification_gates),
                "passed": sum(1 for g in session.verification_gates if g.result == VerificationResult.PASSED),
                "failed": sum(1 for g in session.verification_gates if g.result == VerificationResult.FAILED),
                "needs_review": sum(1 for g in session.verification_gates if g.result == VerificationResult.NEEDS_REVIEW),
            },
            "evaluation": evaluation_engine.get_summary(),
        }
