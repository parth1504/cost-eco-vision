from typing import Dict, Any, List
from datetime import datetime
import logging

from .validator import validate_recommendation
from .executor import execute_boto3_sequence
from .mapper import map_boto3_to_action, list_available_actions

logger = logging.getLogger("actions_agent")


class ActionsAgent:
    """
    Controlled execution planner — NOT a free autonomous agent.
    Validates, maps, and executes whitelisted boto3 operations
    from AI-generated recommendations.
    """

    def apply_selected_fixes(
        self,
        resource_id: str,
        resource_type: str,
        recommendations: List[Dict[str, Any]],
        selected_step_indices: Dict[int, List[int]],
    ) -> Dict[str, Any]:
        """
        Entry point: user selected specific steps from specific recommendations.

        selected_step_indices maps recommendation index → list of step indices
        e.g. {0: [0, 1], 2: [0]} means rec #0 steps 0,1 and rec #2 step 0
        """
        execution_plan = []
        validation_errors = []
        results = []

        for rec_idx, step_indices in selected_step_indices.items():
            if rec_idx >= len(recommendations):
                validation_errors.append(f"Recommendation index {rec_idx} out of range")
                continue

            rec = recommendations[rec_idx]
            rec_title = rec.get("title", f"Recommendation #{rec_idx}")
            boto3_seq = rec.get("boto3_sequence", [])

            if not boto3_seq:
                validation_errors.append(f"'{rec_title}' has no boto3_sequence")
                continue

            ok, errors = validate_recommendation(rec)
            if not ok:
                validation_errors.extend([f"[{rec_title}] {e}" for e in errors])
                continue

            selected_steps = []
            for si in step_indices:
                if si < len(boto3_seq):
                    selected_steps.append(boto3_seq[si])
                else:
                    validation_errors.append(
                        f"[{rec_title}] Step index {si} out of range"
                    )

            if selected_steps:
                execution_plan.append({
                    "recommendation_index": rec_idx,
                    "title": rec_title,
                    "steps": selected_steps,
                })

        if validation_errors and not execution_plan:
            return {
                "status": "validation_failed",
                "errors": validation_errors,
                "results": [],
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

        for plan_item in execution_plan:
            step_results = execute_boto3_sequence(plan_item["steps"])
            results.append({
                "recommendation": plan_item["title"],
                "recommendation_index": plan_item["recommendation_index"],
                "step_results": step_results,
                "all_success": all(r["status"] == "success" for r in step_results),
            })

        all_success = all(r["all_success"] for r in results)

        return {
            "status": "completed" if all_success else "partial_failure",
            "resource_id": resource_id,
            "resource_type": resource_type,
            "results": results,
            "validation_warnings": validation_errors if validation_errors else None,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def preview_plan(
        self,
        recommendations: List[Dict[str, Any]],
        selected_step_indices: Dict[int, List[int]],
    ) -> Dict[str, Any]:
        """Dry-run: returns what would be executed without running anything."""
        plan = []

        for rec_idx, step_indices in selected_step_indices.items():
            if rec_idx >= len(recommendations):
                continue

            rec = recommendations[rec_idx]
            boto3_seq = rec.get("boto3_sequence", [])
            ok, errors = validate_recommendation(rec)

            steps_preview = []
            for si in step_indices:
                if si < len(boto3_seq):
                    step = boto3_seq[si]
                    mapped = map_boto3_to_action(step["service"], step["operation"])
                    steps_preview.append({
                        "step_index": si,
                        "service": step["service"],
                        "operation": step["operation"],
                        "mapped_action": mapped,
                        "would_execute": ok,
                    })

            plan.append({
                "recommendation_index": rec_idx,
                "title": rec.get("title", ""),
                "valid": ok,
                "validation_errors": errors if not ok else [],
                "steps": steps_preview,
            })

        return {"plan": plan}
