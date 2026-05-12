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

from connections.aws import get_client, get_region
from aws.util import get_resource_cost

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

ec2 = get_client("ec2")
cloudwatch = get_client("cloudwatch")
autoscaling = get_client("autoscaling")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# def get_instance_utilization(instance_id, region="us-east-1", start_time=None, end_time=None):
#     """
#     Return latest daily-average CPU utilization (%) over the last 7 days.

#     Notes:
#       - Ignores any caller-supplied window > 7 days. The previous version
#         passed instance launch_time as start_time, which on long-lived
#         instances pulled years of data and (because Datapoints are not
#         chronologically guaranteed) returned a random day's value as 'latest'.
#       - Sorts Datapoints by Timestamp before picking the last one.
#       - Normalises tz-aware inputs (e.g. LaunchTime) to naive UTC so the
#         comparison against `datetime.utcnow()` doesn't blow up.
#     """
#     start_time = _to_naive_utc(start_time)
#     end_time = _to_naive_utc(end_time) or datetime.utcnow()
#     earliest_allowed = end_time - timedelta(days=7)
#     if start_time is None or start_time < earliest_allowed:
#         start_time = earliest_allowed

#     metrics = cloudwatch.get_metric_statistics(
#         Namespace="AWS/EC2",
#         MetricName="CPUUtilization",
#         Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
#         StartTime=start_time,
#         EndTime=end_time,
#         Period=86400,  # 1-day average
#         Statistics=["Average"],
#     )
#     datapoints = sorted(metrics.get("Datapoints", []), key=lambda d: d["Timestamp"])
#     return round(datapoints[-1]["Average"], 2) if datapoints else 0.0

def _to_naive_utc(dt):
    """
    Normalize AWS tz-aware datetimes to naive UTC.
    """

    if dt is None:
        return None

    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)

    return dt


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CloudWatch Metric Fetcher
# ---------------------------------------------------------------------------

def fetch_metric(
    namespace: str,
    metric_name: str,
    dimensions: List[Dict[str, str]],
    statistics: List[str] = ["Average"],
    period: int = 3600,
    days: int = 7,
):
    """
    Generic metric fetcher with:
        - avg
        - max
        - raw datapoints
    """

    try:

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=statistics
        )

        datapoints = sorted(
            response.get("Datapoints", []),
            key=lambda d: d["Timestamp"]
        )

        if not datapoints:
            return {
                "avg": None,
                "max": None,
                "min": None,
                "series": [],
            }

        values = []

        for dp in datapoints:
            for stat in statistics:
                if stat in dp:
                    values.append(dp[stat])

        if not values:
            return {
                "avg": None,
                "max": None,
                "min": None,
                "series": [],
            }

        return {
            "avg": round(sum(values) / len(values), 2),
            "max": round(max(values), 2),
            "min": round(min(values), 2),
            "series": [
                {
                    "timestamp": dp["Timestamp"].isoformat(),
                    "value": next(
                        (
                            dp[s]
                            for s in statistics
                            if s in dp
                        ),
                        None
                    )
                }
                for dp in datapoints
            ]
        }

    except Exception as e:

        print(
            f"Error fetching metric "
            f"{metric_name}: {e}"
        )

        return {
            "avg": None,
            "max": None,
            "min": None,
            "series": [],
        }


# ---------------------------------------------------------------------------
# Security Group Analysis
# ---------------------------------------------------------------------------

def get_open_ports_world(instance) -> List[int]:

    """
    Detect ports exposed to:
        - 0.0.0.0/0
        - ::/0
    """

    open_ports = []

    try:

        security_groups = instance.get(
            "SecurityGroups",
            []
        )

        if not security_groups:
            return []

        sg_ids = [
            sg["GroupId"]
            for sg in security_groups
        ]

        response = ec2.describe_security_groups(
            GroupIds=sg_ids
        )

        for sg in response.get(
            "SecurityGroups",
            []
        ):

            for perm in sg.get(
                "IpPermissions",
                []
            ):

                from_port = perm.get("FromPort")

                if from_port is None:
                    continue

                public = False

                for ipr in perm.get(
                    "IpRanges",
                    []
                ):
                    if ipr.get("CidrIp") == "0.0.0.0/0":
                        public = True

                for ipr in perm.get(
                    "Ipv6Ranges",
                    []
                ):
                    if ipr.get("CidrIpv6") == "::/0":
                        public = True

                if public:
                    open_ports.append(from_port)

        return list(sorted(set(open_ports)))

    except Exception as e:

        print(
            f"Error analyzing security groups: {e}"
        )

        return []


# ---------------------------------------------------------------------------
# AMI Age
# ---------------------------------------------------------------------------

def get_ami_age_days(image_id: Optional[str]):

    if not image_id:
        return None

    try:

        response = ec2.describe_images(
            ImageIds=[image_id]
        )

        images = response.get("Images", [])

        if not images:
            return None

        creation_date = images[0].get(
            "CreationDate"
        )

        if not creation_date:
            return None

        created = datetime.fromisoformat(
            creation_date.replace("Z", "")
        )

        age = (
            datetime.utcnow() - created
        ).days

        return age

    except Exception as e:

        print(f"AMI age error: {e}")

        return None


# ---------------------------------------------------------------------------
# Autoscaling Intelligence
# ---------------------------------------------------------------------------

def get_asg_details(instance_id: str):

    try:

        response = autoscaling.describe_auto_scaling_instances(
            InstanceIds=[instance_id]
        )

        instances = response.get(
            "AutoScalingInstances",
            []
        )

        if not instances:
            return {
                "attached": False,
                "az_count": 0,
                "group_name": None,
            }

        group_name = instances[0].get(
            "AutoScalingGroupName"
        )

        groups = autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[group_name]
        )

        groups = groups.get(
            "AutoScalingGroups",
            []
        )

        if not groups:
            return {
                "attached": True,
                "az_count": 0,
                "group_name": group_name,
            }

        group = groups[0]

        return {
            "attached": True,
            "group_name": group_name,
            "min_size": group.get("MinSize"),
            "max_size": group.get("MaxSize"),
            "desired_capacity": group.get(
                "DesiredCapacity"
            ),
            "az_count": len(
                group.get("AvailabilityZones", [])
            ),
        }

    except Exception as e:

        print(f"ASG lookup error: {e}")

        return {
            "attached": False,
            "az_count": 0,
            "group_name": None,
        }

def get_all_ec2_metrics(
    instance_id,
):

    dimensions = [
        {
            "Name": "InstanceId",
            "Value": instance_id
        }
    ]

    #
    # CPU
    #
    cpu = fetch_metric(
        "AWS/EC2",
        "CPUUtilization",
        dimensions,
        ["Average", "Maximum"]
    )

    #
    # Network
    #
    network_in = fetch_metric(
        "AWS/EC2",
        "NetworkIn",
        dimensions,
        ["Average", "Maximum"]
    )

    network_out = fetch_metric(
        "AWS/EC2",
        "NetworkOut",
        dimensions,
        ["Average", "Maximum"]
    )

    #
    # Packets
    #
    packets_in = fetch_metric(
        "AWS/EC2",
        "NetworkPacketsIn",
        dimensions,
        ["Average", "Maximum"]
    )

    packets_out = fetch_metric(
        "AWS/EC2",
        "NetworkPacketsOut",
        dimensions,
        ["Average", "Maximum"]
    )

    #
    # Disk
    #
    disk_read = fetch_metric(
        "AWS/EC2",
        "DiskReadOps",
        dimensions,
        ["Average", "Maximum"]
    )

    disk_write = fetch_metric(
        "AWS/EC2",
        "DiskWriteOps",
        dimensions,
        ["Average", "Maximum"]
    )

    #
    # Status checks
    #
    status_check = fetch_metric(
        "AWS/EC2",
        "StatusCheckFailed",
        dimensions,
        ["Average", "Maximum"]
    )

    #
    # CWAgent metrics
    #
    memory = fetch_metric(
        "CWAgent",
        "mem_used_percent",
        dimensions,
        ["Average", "Maximum"]
    )

    swap = fetch_metric(
        "CWAgent",
        "swap_used_percent",
        dimensions,
        ["Average", "Maximum"]
    )

    disk_used = fetch_metric(
        "CWAgent",
        "disk_used_percent",
        dimensions,
        ["Average", "Maximum"]
    )

    tcp_conn = fetch_metric(
        "CWAgent",
        "tcp_established",
        dimensions,
        ["Average", "Maximum"]
    )

    processes = fetch_metric(
        "CWAgent",
        "processes_total",
        dimensions,
        ["Average", "Maximum"]
    )

    #
    # Build final metrics object
    #
    return {

        "cpu": {
            "avg_7d": cpu["avg"],
            "max_7d": cpu["max"],
            "series": cpu["series"],
        },

        "memory_avg_7d": memory["avg"],
        "memory_max_7d": memory["max"],

        "swap_avg_7d": swap["avg"],
        "swap_max_7d": swap["max"],

        "disk_used_avg": disk_used["avg"],
        "disk_used_max": disk_used["max"],

        "network": {

            "in_avg_7d":
                network_in["avg"],

            "in_peak_7d":
                network_in["max"],

            "out_avg_7d":
                network_out["avg"],

            "out_peak_7d":
                network_out["max"],

            "packets_in_avg":
                packets_in["avg"],

            "packets_out_avg":
                packets_out["avg"],
        },

        "disk": {

            "read_avg_7d":
                disk_read["avg"],

            "read_peak_7d":
                disk_read["max"],

            "write_avg_7d":
                disk_write["avg"],

            "write_peak_7d":
                disk_write["max"],
        },

        "health": {

            "status_check_failed_avg":
                status_check["avg"],

            "status_check_failed_max":
                status_check["max"],
        },

        "tcp_conn_avg":
            tcp_conn["avg"],

        "tcp_conn_max":
            tcp_conn["max"],

        "process_avg":
            processes["avg"],

        "process_max":
            processes["max"],

        #
        # Mocked latency for now
        #
        "p95_avg": None,
        "p95_max": None,

        "p99_avg": None,
        "p99_max": None,

        #
        # Placeholder operational signals
        #
        "packet_drops_avg": None,
        "packet_drops_max": None,

        "ebs_burst_avg": None,
        "ebs_burst_min": None,
    }

def get_config_data(instance):
    """
    Extract config signals that need data we don't have.
    """
    instance_id = instance.get("InstanceId")
    image_id = instance.get("ImageId")

    ami_age_days = get_ami_age_days(
        image_id
    )

    asg = get_asg_details(
        instance_id
    )

    open_ports = get_open_ports_world(
        instance
    )
    config = {
        "instance_type": instance.get("InstanceType"),
        "is_spot": instance.get("InstanceLifecycle") == "spot",
        "is_reserved": False,  # Placeholder - requires separate API call or tag convention
        "imdsv2_required": None,  # Placeholder - would require DescribeInstanceAttribute calls
        "ebs_encrypted": None,  # Placeholder - would require DescribeVolumes calls
        "public_ip": bool(instance.get("PublicIpAddress")),
        "open_ports_world": get_open_ports_world(instance),
        "ami_age_days": get_ami_age_days(instance.get("ImageId")),
        "autoscaling_attached": asg["attached"],
        "autoscaling_az_count": asg["az_count"],
    }
    return config

def build_ec2_resource(instance):
    """
    Build enriched EC2 resource object
    for the SRE intelligence pipeline.
    """

    instance_id = instance.get("InstanceId")
    instance_type = instance.get(
        "InstanceType",
        "unknown"
    )
    launch_time = instance.get(
        "LaunchTime"
    )
    name_tag = next(
        (
            tag["Value"]
            for tag in instance.get(
                "Tags",
                []
            )
            if tag["Key"] == "Name"
        ),
        "Unnamed-Instance"
    )
    return {

        "resource_id": instance.get("InstanceId"),
        "name": name_tag,
        "type": "EC2",
        "provider": "AWS",
        "status": instance.get("State",{}).get("Name","unknown").lower(),
        "region":  get_region(),
        "monthly_cost": get_resource_cost("InstanceId",instance_id),
        "tags": {
            t["Key"]: t["Value"]
            for t in instance.get(
                "Tags",
                []
            )
        },
        "metrics": get_all_ec2_metrics(instance_id= instance_id),
        "config": get_config_data(instance),
        "creation_date":
            launch_time.isoformat()
            if launch_time else None,
        "last_agent_run":
            datetime.utcnow().isoformat(),
        "is_optimized": False,
    }

    