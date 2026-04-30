from backend.connections.aws import get_client
from backend.services.recommendations import get_resource_from_db, save_resource_in_db
from backend.aws.util import replace_placeholders, get_resource_cost

from datetime import datetime, timedelta
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
async def list_ec2_instances():
    """Fetch all EC2 instances and enrich with DynamoDB-backed state."""
    try:
        response = ec2.describe_instances()
        instances = []
        

        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):

                instance_id = instance.get("InstanceId")
                
                # --- CHECK DYNAMODB ---
                db_item = get_resource_from_db(instance_id, "EC2")
                
                if db_item:
                    # Load stored fields (important for state persistence)
                    instance_data=db_item
                    instance_data['resource_id']=instance_id
                else:
                    # Save new record
                    state = instance.get("State", {}).get("Name", "unknown")
                    instance_type = instance.get("InstanceType", "unknown")
                    region = ec2.meta.region_name
                    launch_time = instance.get("LaunchTime")

                    name_tag = next(
                        (tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"),
                        "Unnamed-Instance"
                    )

                    utilization = get_instance_utilization(instance_id, region, launch_time)
                    cost = get_resource_cost("InstanceId", instance_id)

                    # Base object
                    instance_data = {
                        "resource_id": instance_id,
                        "name": name_tag,
                        "type": "EC2",
                        "status": state.lower(),
                        "utilization": utilization,
                        "monthly_cost": cost,
                        "region": region,
                        "provider": "AWS",
                        "is_optimized": False,
                        "last_activity": launch_time.isoformat() if launch_time else None,
                        "creation_date": launch_time.isoformat() if launch_time else None,
                        "recommendations": replace_placeholders(
                        ec2_recommendations,
                        {"INSTANCE_ID": instance_id}
                    )
                    }

                    saved = save_resource_in_db(instance_id, "EC2", instance_data)

                instances.append(instance_data)

        return instances

    except Exception as e:
        print(f"Error in list_ec2_instances: {e}")
        return []

def get_instance_utilization(instance_id, region="eu-north-1",start_time=None,end_time=None):
    end_time = datetime.utcnow()

    metrics = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start_time,
        EndTime=end_time,
        Period=86400,  # 1-day average
        Statistics=["Average"]
    )
    datapoints = metrics.get("Datapoints", [])
    return round(datapoints[-1]["Average"], 2) if datapoints else 0.0
