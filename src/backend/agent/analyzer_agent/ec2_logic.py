from agent.llm.llm_client import get_llm_client

def generate_ec2_recommendations(resource):
    from datetime import datetime, timedelta

    recommendations = []

    # --- Extract values safely ---
    metrics = resource.get("metrics", {})
    cpu = metrics.get("cpu", {})
    network = metrics.get("network", {})
    health = metrics.get("health", {})
    config = resource.get("config", {})

    cpu_avg = cpu.get("avg_7d")
    cpu_max = cpu.get("max_7d")
    net_in = network.get("in_avg_7d", 0)
    net_out = network.get("out_avg_7d", 0)
    net_total = (net_in or 0) + (net_out or 0)

    instance_type = config.get("instance_type", "")
    instance_id = "{INSTANCE_ID}"

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

    if instance_type in ["t3.micro", "t2.micro"]:
        skip_small_instance = True
    else:
        skip_small_instance = False

    llm = get_llm_client()

    # --- RULE 3: IDLE INSTANCE ---
    if cpu_avg < 5 and net_total < 10:
        confidence = min(1.0, 0.5 + 0.3 + 0.2)

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
                    "command": "aws ec2 stop-instances --instance-ids {INSTANCE_ID}",
                    "description": "Stop the EC2 instance to eliminate unnecessary cost."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "ec2",
                    "operation": "stop_instances",
                    "params": {"InstanceIds": [instance_id]}
                }
            ],
            "confidence": confidence,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Idle instance detected"
            }
        })

    # --- RULE 2: BURSTY WORKLOAD ---
    if cpu_avg < 20 and cpu_max > 70:
        confidence = min(1.0, 0.4 + 0.4)

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
            "solution_steps": [
                {
                    "step": 1,
                    "command": "Configure Auto Scaling Group",
                    "description": "Set up auto scaling to handle workload spikes dynamically."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "autoscaling",
                    "operation": "create_auto_scaling_group",
                    "params": {}
                }
            ],
            "confidence": confidence,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Bursty workload detected"
            }
        })

    # --- RULE 1: UNDERUTILIZED ---
    if cpu_avg < 20 and cpu_max < 50 and net_total < 100:
        if cpu_max > 70 or skip_small_instance:
            pass
        else:
            confidence = min(1.0, 0.4 + 0.3 + 0.3)

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
                        "command": "aws ec2 modify-instance-attribute --instance-id {INSTANCE_ID} --instance-type t3.micro",
                        "description": "Change instance type to smaller size."
                    }
                ],
                "boto3_sequence": [
                    {
                        "service": "ec2",
                        "operation": "modify_instance_attribute",
                        "params": {
                            "InstanceId": instance_id,
                            "InstanceType": {"Value": "t3.micro"}
                        }
                    }
                ],
                "confidence": confidence,
                "reasoning": {
                    "cpu_avg": cpu_avg,
                    "cpu_max": cpu_max,
                    "network": net_total,
                    "decision": "Underutilized instance"
                }
            })

    # --- RULE 4: OVERUTILIZED ---
    if cpu_max > 80:
        confidence = min(1.0, 0.5 + 0.3)

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
                    "command": "aws ec2 modify-instance-attribute --instance-id {INSTANCE_ID} --instance-type t3.large",
                    "description": "Upgrade instance type to handle load."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "ec2",
                    "operation": "modify_instance_attribute",
                    "params": {
                        "InstanceId": instance_id,
                        "InstanceType": {"Value": "t3.large"}
                    }
                }
            ],
            "confidence": confidence,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Overutilized instance"
            }
        })

    # --- RULE 5: HEALTH ISSUE ---
    if health.get("status_check_failed_max", 0) > 0:
        confidence = 0.9

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
                    "command": "aws ec2 reboot-instances --instance-ids {INSTANCE_ID}",
                    "description": "Reboot instance to recover from failure."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "ec2",
                    "operation": "reboot_instances",
                    "params": {"InstanceIds": [instance_id]}
                }
            ],
            "confidence": confidence,
            "reasoning": {
                "cpu_avg": cpu_avg,
                "cpu_max": cpu_max,
                "network": net_total,
                "decision": "Health issue detected"
            }
        })

    return recommendations