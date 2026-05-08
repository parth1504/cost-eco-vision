from connections.aws import get_client, get_region
from connections.db import get_resource_from_db, save_resource_in_db
from aws.util import  get_resource_cost, should_run_agent
from datetime import datetime, timedelta
from agent.analyzer_agent.main import generateRecommendations


ec2 = get_client("ec2")
cloudwatch = get_client("cloudwatch")


ec2_recommendations = [
    {
        "title": "Instance Underutilized — Right-size to t3.micro",
        "description": (
            "The instance has consistently low CPU and network utilization for the last 7 days. "
            "Downsizing to a smaller instance type can significantly reduce cost without affecting performance."
        ),
        "type": "cost",
        "severity": "warning",
        "saving": 4.23,  # monthly savings estimate
        "issue": "Low CPU utilization (<20%) detected for 7 days",
        "impact": "medium",
        "status": "active",
        "solution_steps": [
            {
                "step": 1,
                "command": "aws ec2 stop-instances --instance-ids {INSTANCE_ID}",
                
                "description": "Stops the EC2 instance before changing instance type."
            },
            {
                "step": 2,
                "command": "aws ec2 modify-instance-attribute --instance-id {INSTANCE_ID} --instance-type \"t3.micro\"",
                "description": "Modifies the instance type to a more cost-efficient size."
            },
            {
                "step": 3,
                "command": "aws ec2 start-instances --instance-ids {INSTANCE_ID}",
                "description": "Restarts the instance after applying the change."
            }
        ],
        "boto3_sequence": [
            {
                "service": "ec2",
                "operation": "stop_instances",
                "params": { "InstanceIds": ["{INSTANCE_ID}"] }
            },
            {
                "service": "ec2",
                "operation": "modify_instance_attribute",
                "params": {
                    "InstanceId": "{INSTANCE_ID}",
                    "InstanceType": { "Value": "t3.micro" }
                }
            },

            {
                "service": "ec2",
                "operation": "start_instances",
                "params": { "InstanceIds": ["{INSTANCE_ID}"] }
            }
            ]
    },

    {
        "title": "Instance Missing Detailed Monitoring",
        "description": (
            "The instance is using basic monitoring which provides fewer metrics at 5-minute intervals. "
            "Enabling detailed monitoring provides 1-minute metrics for more accurate auto scaling and alerting."
        ),
        "type": "performance",
        "severity": "info",
        "saving": "N/A",
        "status": "active",
        "issue": "Detailed monitoring is disabled",
        "impact": "low",
        "solution_steps": [
            {
                "step": 1,
                "command": "aws ec2 monitor-instances --instance-ids {INSTANCE_ID}",
                "description": "Enables detailed 1-minute CloudWatch monitoring for the EC2 instance."
            }
        ],
        "boto3_sequence": [
            {
                "service": "ec2",
                "operation": "monitor_instances",
                "params": {
                "InstanceIds": ["{INSTANCE_ID}"]
                }
            }
            ]

    },

   
]
# ---------- EC2 ----------
async def list_ec2_instances(force: bool = False):
    """
    Fetch all EC2 instances and enrich with DynamoDB-backed state.

    Pass force=True to bypass the cooldown and force a fresh agent re-run.
    On re-run we now re-fetch live metrics+config from AWS rather than
    feeding stale cached fields to the agent.
    """
    try:
        response = ec2.describe_instances()
        instances = []

        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):

                instance_id = instance.get("InstanceId")

                # --- CHECK DYNAMODB ---
                db_item = get_resource_from_db(instance_id, "EC2")
                if db_item:
                    last_run = db_item.get("last_agent_run")
                    print(f"EC2 {instance_id} - last agent run: {last_run}, force={force}")

                    if should_run_agent(last_run, force=force):
                        # Build fresh from live AWS data, then preserve any
                        # human-set / persisted state (is_optimized).
                        instance_data = build_ec2_resource(instance)
                        instance_data["is_optimized"] = db_item.get("is_optimized", False)
                        recommendations = generateRecommendations(instance_data)
                        instance_data["recommendations"] = recommendations
                        instance_data["last_agent_run"] = datetime.utcnow().isoformat()
                        save_resource_in_db(instance_id, "EC2", instance_data)
                    else:
                        # Within cooldown → return cached as-is.
                        instance_data = db_item
                        instance_data["resource_id"] = instance_id
                else:
                    instance_data = build_ec2_resource(instance)
                    recommendations = generateRecommendations(instance_data)
                    instance_data["recommendations"] = recommendations
                    save_resource_in_db(instance_data["resource_id"], "EC2", instance_data)

                instances.append(instance_data)

        return instances

    except Exception as e:
        print(f"Error in list_ec2_instances: {e}")
        return []

def build_ec2_resource(instance):
    instance_id = instance.get("InstanceId")
    state = instance.get("State", {}).get("Name", "unknown")
    instance_type = instance.get("InstanceType", "unknown")
    region = get_region()
    launch_time = instance.get("LaunchTime")
    name_tag = next(
        (tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"),
        "Unnamed-Instance"
    )

    utilization = get_instance_utilization(instance_id, region, launch_time)
    cost = get_resource_cost("InstanceId", instance_id)
    metrics = get_all_ec2_metrics(instance_id, cloudwatch)

    return {
        "resource_id": instance_id,
        "name": name_tag,
        "type": "EC2",
        "status": state.lower(),
        "utilization": utilization,
        "metrics": metrics,
        "config": {
            "instance_type": instance_type
        },
        "monthly_cost": cost,
        "region": region,
        "provider": "AWS",
        "is_optimized": False,
        "last_agent_run": datetime.utcnow().isoformat(),
        "creation_date": launch_time.isoformat() if launch_time else None,
        
    }

def _to_naive_utc(dt):
    """Normalise a datetime to naive UTC. AWS returns tz-aware datetimes
    (e.g. instance.LaunchTime), but the rest of this codebase uses
    `datetime.utcnow()` (naive). Mixing them in comparisons crashes."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def get_instance_utilization(instance_id, region="us-east-1", start_time=None, end_time=None):
    """
    Return latest daily-average CPU utilization (%) over the last 7 days.

    Notes:
      - Ignores any caller-supplied window > 7 days. The previous version
        passed instance launch_time as start_time, which on long-lived
        instances pulled years of data and (because Datapoints are not
        chronologically guaranteed) returned a random day's value as 'latest'.
      - Sorts Datapoints by Timestamp before picking the last one.
      - Normalises tz-aware inputs (e.g. LaunchTime) to naive UTC so the
        comparison against `datetime.utcnow()` doesn't blow up.
    """
    start_time = _to_naive_utc(start_time)
    end_time = _to_naive_utc(end_time) or datetime.utcnow()
    earliest_allowed = end_time - timedelta(days=7)
    if start_time is None or start_time < earliest_allowed:
        start_time = earliest_allowed

    metrics = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start_time,
        EndTime=end_time,
        Period=86400,  # 1-day average
        Statistics=["Average"],
    )
    datapoints = sorted(metrics.get("Datapoints", []), key=lambda d: d["Timestamp"])
    return round(datapoints[-1]["Average"], 2) if datapoints else 0.0

def get_all_ec2_metrics(instance_id, cloudwatch_client):
    """
    Fetch all relevant EC2 metrics for last 7 days.
    Returns aggregated + optional time series for agent use.
    """

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=7)

    def fetch_metric(metric_name, statistics=["Average"]):
        try:
            response = cloudwatch_client.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName=metric_name,
                Dimensions=[
                    {'Name': 'InstanceId', 'Value': instance_id}
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,
                Statistics=statistics
            )

            datapoints = response.get("Datapoints", [])

            if not datapoints:
                return None, None

            values = []
            for dp in datapoints:
                for stat in statistics:
                    if stat in dp:
                        values.append(dp[stat])

            if not values:
                return None, None

            avg = round(sum(values) / len(values), 2)
            peak = round(max(values), 2)

            return avg, peak

        except Exception as e:
            print(f"Error fetching {metric_name} for {instance_id}: {e}")
            return None, None

    # ------------------------
    # CPU
    # ------------------------
    cpu_avg, cpu_max = fetch_metric("CPUUtilization", ["Average", "Maximum"])

    # ------------------------
    # Network
    # ------------------------
    net_in_avg, net_in_max = fetch_metric("NetworkIn")
    net_out_avg, net_out_max = fetch_metric("NetworkOut")

    # ------------------------
    # Disk IO
    # ------------------------
    disk_read_avg, disk_read_max = fetch_metric("DiskReadOps")
    disk_write_avg, disk_write_max = fetch_metric("DiskWriteOps")

    # ------------------------
    # Status Checks (Health)
    # ------------------------
    status_check_avg, status_check_max = fetch_metric("StatusCheckFailed")

    # ------------------------
    # Build final object
    # ------------------------
    metrics = {
        "cpu": {
            "avg_7d": cpu_avg,
            "max_7d": cpu_max
        },
        "network": {
            "in_avg_7d": net_in_avg,
            "in_peak_7d": net_in_max,
            "out_avg_7d": net_out_avg,
            "out_peak_7d": net_out_max
        },
        "disk": {
            "read_avg_7d": disk_read_avg,
            "read_peak_7d": disk_read_max,
            "write_avg_7d": disk_write_avg,
            "write_peak_7d": disk_write_max
        },
        "health": {
            "status_check_failed_avg": status_check_avg,
            "status_check_failed_max": status_check_max
        }
    }

    return metrics