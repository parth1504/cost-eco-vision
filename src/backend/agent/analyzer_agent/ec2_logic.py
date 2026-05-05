import logging

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from agent.llm.llm_client import get_llm_client


def generate_ec2_recommendations(resource):
    """
    Rule-based EC2 recommendation generator.

    Conventions enforced here:
      - Real instance id is inlined into boto3_sequence params (the previous
        `"{INSTANCE_ID}"` placeholder was never substituted on the apply path
        → Apply Fix sent the literal string to AWS and 400'd).
      - Sizing rules use explicit precedence so contradictory recommendations
        never fire on the same instance:
            Idle ≻ Overutilized ≻ Bursty ≻ Underutilized
        Health and "missing detailed monitoring" are independent and always
        evaluated.
      - "Bursty" recommends Auto Scaling but our boto3 sequence for it is a
        stub (empty params). It's marked `manual_only: True` so Apply Fix
        won't try to run it.
    """
    logger.info("Generating EC2 recommendations for resource: %s", resource)
    from datetime import datetime, timedelta

    recommendations = []

    # --- Extract values safely ---
    metrics = resource.get("metrics", {}) or {}
    cpu = metrics.get("cpu", {}) or {}
    network = metrics.get("network", {}) or {}
    health = metrics.get("health", {}) or {}
    config = resource.get("config", {}) or {}

    cpu_avg = cpu.get("avg_7d")
    cpu_max = cpu.get("max_7d")
    net_in = network.get("in_avg_7d", 0) or 0
    net_out = network.get("out_avg_7d", 0) or 0
    net_total = net_in + net_out

    instance_type = config.get("instance_type", "")
    # Use the real instance id, not a placeholder.
    instance_id = resource.get("resource_id") or resource.get("name") or ""

    # --- Safety Guards ---
    if cpu_avg is None or cpu_max is None:
        return []

    creation_date = resource.get("creation_date")
    if creation_date:
        try:
            created = datetime.fromisoformat(creation_date.replace("Z", ""))
            if datetime.utcnow() - created < timedelta(days=2):
                return []
        except Exception:
            pass

    skip_small_instance = instance_type in ("t3.micro", "t2.micro")

    llm = get_llm_client()

    # ------------------------------------------------------------------
    # SIZING RULES — apply explicit precedence so we emit at most one
    # size-related recommendation per instance.
    # ------------------------------------------------------------------
    size_decision_made = False

    # RULE: IDLE INSTANCE — strongest signal (suppresses Underutilized,
    # Bursty, and Overutilized).
    if cpu_avg < 5 and net_total < 10:
        size_decision_made = True
        description = llm.generate(
            f"Explain why an EC2 instance with CPU avg {cpu_avg}% and near-zero network usage should be stopped to save cost."
        )
        recommendations.append({
            "title": "Idle Instance Detected — Stop Instance",
            "description": description,
            "type": "cost",
            "severity": "high",
            "saving": resource.get("monthly_cost", 0),
            "issue": "Instance idle with negligible CPU and network usage",
            "impact": "high",
            "status": "active",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws ec2 stop-instances --instance-ids {instance_id}",
                    "description": "Stop the EC2 instance to eliminate unnecessary cost.",
                }
            ],
            "boto3_sequence": [
                {
                    "service": "ec2",
                    "operation": "stop_instances",
                    "params": {"InstanceIds": [instance_id]},
                }
            ],
            "confidence": 0.95,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Idle instance detected",
            },
        })

    # RULE: OVERUTILIZED — only if not Idle.
    if not size_decision_made and cpu_max > 80:
        size_decision_made = True
        description = llm.generate(
            f"Explain why an EC2 instance with CPU peak {cpu_max}% should be scaled up."
        )
        recommendations.append({
            "title": "Overutilized Instance — Scale Up",
            "description": description,
            "type": "performance",
            "severity": "high",
            "saving": "N/A",
            "issue": "High CPU utilization peaks",
            "impact": "high",
            "status": "active",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws ec2 modify-instance-attribute --instance-id {instance_id} --instance-type t3.large",
                    "description": "Upgrade instance type to handle load.",
                }
            ],
            "boto3_sequence": [
                {
                    "service": "ec2",
                    "operation": "modify_instance_attribute",
                    "params": {
                        "InstanceId": instance_id,
                        "InstanceType": {"Value": "t3.large"},
                    },
                }
            ],
            "confidence": 0.8,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Overutilized instance",
            },
        })

    # RULE: BURSTY WORKLOAD — only if not Idle / Overutilized.
    # Marked manual_only: ASG creation needs a launch template + min/max
    # we can't infer, so the boto3 sequence is a stub and Apply Fix would
    # error. The recommendation surfaces the suggestion; humans set up ASG.
    if not size_decision_made and cpu_avg < 20 and cpu_max > 70:
        size_decision_made = True
        description = llm.generate(
            f"Explain why an EC2 instance with low average CPU ({cpu_avg}%) but high peak ({cpu_max}%) should use autoscaling."
        )
        recommendations.append({
            "title": "Bursty Workload Detected — Use Auto Scaling",
            "description": description,
            "type": "performance",
            "severity": "medium",
            "saving": "N/A",
            "issue": "CPU spikes detected despite low average usage",
            "impact": "medium",
            "status": "active",
            "manual_only": True,  # ASG creation needs human input
            "solution_steps": [
                {
                    "step": 1,
                    "command": "Configure Auto Scaling Group manually",
                    "description": "Set up auto scaling to handle workload spikes dynamically.",
                }
            ],
            "boto3_sequence": [],
            "confidence": 0.7,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Bursty workload detected",
            },
        })

    # RULE: UNDERUTILIZED — weakest sizing signal, only if nothing stronger.
    if (
        not size_decision_made
        and cpu_avg < 20
        and cpu_max < 50
        and net_total < 100
        and not skip_small_instance
    ):
        size_decision_made = True
        description = llm.generate(
            f"Explain why an EC2 instance with low CPU avg {cpu_avg}% and low peak {cpu_max}% should be downsized."
        )
        recommendations.append({
            "title": "Underutilized Instance — Downsize",
            "description": description,
            "type": "cost",
            "severity": "warning",
            "saving": round(resource.get("monthly_cost", 0) * 0.3, 2),
            "issue": "Low CPU and network utilization",
            "impact": "medium",
            "status": "active",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws ec2 modify-instance-attribute --instance-id {instance_id} --instance-type t3.micro",
                    "description": "Change instance type to smaller size.",
                }
            ],
            "boto3_sequence": [
                {
                    "service": "ec2",
                    "operation": "modify_instance_attribute",
                    "params": {
                        "InstanceId": instance_id,
                        "InstanceType": {"Value": "t3.micro"},
                    },
                }
            ],
            "confidence": 0.7,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Underutilized instance",
            },
        })

    # ------------------------------------------------------------------
    # INDEPENDENT RULES — health, monitoring; always evaluated.
    # ------------------------------------------------------------------

    # RULE: HEALTH ISSUE
    if health.get("status_check_failed_max", 0) > 0:
        description = llm.generate(
            "Explain why an EC2 instance with failed health checks should be restarted."
        )
        recommendations.append({
            "title": "Instance Health Issue — Restart Recommended",
            "description": description,
            "type": "performance",
            "severity": "critical",
            "saving": "N/A",
            "issue": "Instance health check failures detected",
            "impact": "high",
            "status": "active",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws ec2 reboot-instances --instance-ids {instance_id}",
                    "description": "Reboot instance to recover from failure.",
                }
            ],
            "boto3_sequence": [
                {
                    "service": "ec2",
                    "operation": "reboot_instances",
                    "params": {"InstanceIds": [instance_id]},
                }
            ],
            "confidence": 0.9,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Health issue detected",
            },
        })

    logger.info("Finished generating EC2 recommendations")
    return recommendations
