"""
Explainability service — generates reasoning, evidence, and assumptions
for every optimization recommendation using LLM + deterministic analysis.

Every computed output (cost, latency, recommendation) gets an explainability
payload that can be revealed via UI interaction without cluttering the default view.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agent.llm.llm_client import get_llm_client
from services.simulation import infer_system_characteristics

logger = logging.getLogger(__name__)


def generate_explainability(
    section: str,
    simulation_data: Dict[str, Any],
    resources: List[Dict],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate explainability payload for a given optimization section.
    Returns reasoning, evidence, and assumptions.
    """
    chars = infer_system_characteristics(resources)

    evidence = _gather_evidence(section, simulation_data, resources, chars)
    assumptions = _gather_assumptions(section, config, chars)

    reasoning = _generate_reasoning_llm(section, simulation_data, evidence, assumptions, chars)

    return {
        "reasoning": reasoning,
        "evidence": evidence,
        "assumptions": assumptions,
        "system_profile": {
            "latency_sensitivity": chars["latency_sensitivity"],
            "fragility": chars["fragility"],
            "retry_behavior": chars["retry_behavior"],
        },
    }


def _gather_evidence(
    section: str,
    sim: Dict[str, Any],
    resources: List[Dict],
    chars: Dict,
) -> List[Dict[str, str]]:
    """Collect concrete evidence signals used in the recommendation."""
    evidence = []

    if section == "right_sizing":
        dev = sim.get("developer", {})
        exec_view = sim.get("executive", {})

        if dev.get("latency_increase_pct", 0) > 10:
            evidence.append({
                "signal": "latency_threshold",
                "description": f"Latency projected to increase {dev['latency_increase_pct']}% — system shows latency sensitivity of {chars['latency_sensitivity']:.0%}",
                "severity": "warning" if dev["latency_increase_pct"] < 25 else "critical",
            })

        if dev.get("retry_amplification_factor", 1) > 1.3:
            evidence.append({
                "signal": "retry_amplification",
                "description": f"Retry rate will amplify by {dev['retry_amplification_factor']}x due to network variability patterns in metrics",
                "severity": "warning",
            })

        if chars["fragility"] > 0.5:
            evidence.append({
                "signal": "system_fragility",
                "description": f"System fragility score is {chars['fragility']:.0%} — multiple unresolved recommendations indicate instability",
                "severity": "warning",
            })

        if sim.get("capacity_reduction_pct", 0) > 25:
            evidence.append({
                "signal": "aggressive_reduction",
                "description": f"Capacity reduction of {sim['capacity_reduction_pct']}% exceeds safe threshold for production workloads",
                "severity": "critical",
            })

        if not evidence:
            evidence.append({
                "signal": "nominal",
                "description": "All metrics within safe operating bounds — no adverse patterns detected",
                "severity": "info",
            })

    elif section == "auto_scaling":
        dev = sim.get("developer", {})

        if dev.get("scaling_events_per_day", 0) > 8:
            evidence.append({
                "signal": "high_churn",
                "description": f"Projected {dev['scaling_events_per_day']} scaling events/day may cause instability and cold-start penalties",
                "severity": "warning",
            })

        if dev.get("spike_latency_increase_pct", 0) > 15:
            evidence.append({
                "signal": "scaling_lag",
                "description": f"During scale-up lag, latency spikes projected at +{dev['spike_latency_increase_pct']}% based on peak-to-mean ratio",
                "severity": "warning",
            })

        if dev.get("stability_score", 10) < 5:
            evidence.append({
                "signal": "stability_degradation",
                "description": f"Stability score drops to {dev['stability_score']}/10 — frequent scaling creates debugging complexity",
                "severity": "warning",
            })

        over_waste = sim.get("executive", {}).get("over_provisioning_waste", 0)
        if over_waste > 0:
            evidence.append({
                "signal": "over_provisioning",
                "description": f"Current over-provisioning waste: ${over_waste}/mo — sensitivity increase can reclaim this",
                "severity": "info",
            })

        if not evidence:
            evidence.append({
                "signal": "nominal",
                "description": "Scaling configuration is balanced — no adverse patterns detected",
                "severity": "info",
            })

    return evidence


def _gather_assumptions(
    section: str,
    config: Dict[str, Any],
    chars: Dict,
) -> List[str]:
    """Document assumptions underlying the simulation."""
    assumptions = []

    if section == "right_sizing":
        level = config.get("right_sizing_level", 70)
        assumptions.append(f"Optimization level {level}% maps linearly to capacity reduction (0-40% range)")
        assumptions.append("Critical components (>40% of total spend) receive 30% damping on aggressive optimization")
        assumptions.append(f"Latency sensitivity ({chars['latency_sensitivity']:.0%}) derived from average CPU utilization across compute fleet")
        assumptions.append("Retry amplification modeled from network metric variability (max/avg ratio > 3x = retry-prone)")
        if chars["fragility"] > 0.3:
            assumptions.append(f"System fragility ({chars['fragility']:.0%}) inferred from unresolved recommendation density")

    elif section == "auto_scaling":
        sens = config.get("auto_scaling_level", 5)
        assumptions.append(f"Sensitivity {sens}/10 controls cooldown (300s→120s) and thresholds (60%→80% scale-up)")
        assumptions.append("Over-provisioning waste baseline assumed at 15% of total compute cost")
        assumptions.append("Scaling events increase linearly with sensitivity (2 base + 12 × sensitivity fraction)")
        assumptions.append("Under-scaling cost modeled as quadratic with sensitivity (risk grows nonlinearly)")

    return assumptions


def _generate_reasoning_llm(
    section: str,
    sim: Dict[str, Any],
    evidence: List[Dict],
    assumptions: List[str],
    chars: Dict,
) -> str:
    """Use LLM to generate natural-language reasoning summary."""
    try:
        llm = get_llm_client()

        evidence_text = "\n".join(f"- [{e['severity']}] {e['description']}" for e in evidence)
        assumptions_text = "\n".join(f"- {a}" for a in assumptions)

        section_label = "Resource Right-Sizing" if section == "right_sizing" else "Auto-Scaling Optimization"
        risk_zone = sim.get("risk_zone", "unknown")
        exec_data = sim.get("executive", {})

        prompt = f"""You are an infrastructure optimization advisor. Generate a concise 2-3 sentence reasoning explanation for why this optimization recommendation was made.

Section: {section_label}
Risk Zone: {risk_zone}
Cost Savings: ${exec_data.get('cost_savings_monthly', 0)}/month
System Profile: latency_sensitivity={chars['latency_sensitivity']}, fragility={chars['fragility']}, retry_behavior={chars['retry_behavior']}

Evidence signals:
{evidence_text}

Key assumptions:
{assumptions_text}

Write a clear, technical but accessible explanation of WHY this recommendation level is classified as "{risk_zone}" and what the user should consider. Be specific about which signals drove the assessment. Do NOT use bullet points — write flowing prose. Max 3 sentences."""

        result = llm.generate(prompt)
        return result.strip() if result else _fallback_reasoning(section, sim, chars)

    except Exception as e:
        logger.warning(f"LLM reasoning generation failed: {e}")
        return _fallback_reasoning(section, sim, chars)


def _fallback_reasoning(section: str, sim: Dict, chars: Dict) -> str:
    """Deterministic fallback when LLM is unavailable."""
    risk = sim.get("risk_zone", "unknown")

    if section == "right_sizing":
        if risk == "safe":
            return f"At this optimization level, capacity reduction stays within safe bounds. System latency sensitivity ({chars['latency_sensitivity']:.0%}) and fragility ({chars['fragility']:.0%}) are both low enough to absorb the change without measurable impact on error rates or retry behavior."
        elif risk == "moderate":
            return f"This level approaches the threshold where latency-sensitive systems may experience degradation. With a system fragility of {chars['fragility']:.0%}, some retry amplification is expected during peak load periods."
        else:
            return f"Aggressive right-sizing at this level will likely cause measurable latency increases and error rate spikes. The system's latency sensitivity ({chars['latency_sensitivity']:.0%}) combined with high capacity reduction makes this unsuitable for production workloads without staged rollout."

    elif section == "auto_scaling":
        if risk == "safe":
            return f"Scaling sensitivity is conservative enough to maintain stability (score: {sim.get('developer', {}).get('stability_score', 'N/A')}/10). The system will react to load changes without excessive churn or cold-start penalties."
        elif risk == "moderate":
            return f"At this sensitivity, scaling frequency increases noticeably. The system may experience brief latency spikes during scale-up transitions, particularly given the retry behavior factor of {chars['retry_behavior']:.0%}."
        else:
            return f"High sensitivity creates rapid scaling oscillations that can destabilize the system. Expected {sim.get('developer', {}).get('scaling_events_per_day', 'N/A')} events/day creates debugging complexity and potential cascading failures during traffic spikes."

    return "Insufficient data to generate detailed reasoning."
