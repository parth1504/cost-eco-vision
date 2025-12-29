from resources import get_resource_from_db
from dynamo import save_resource_in_db, convert_floats
from datetime import datetime

async def list_cloud_storage():
    # --- Try loading from DynamoDB ---
    db_item = get_resource_from_db("gcp-sql-01", "CloudSQL")
                
    if db_item:
        # Convert DynamoDB decimals → floats
        instance_data = convert_floats(db_item)
        return [instance_data]

    # --- If not found, create new mock GCP resource ---
    state = "running"
    instance_type = "CloudSQL"
    region = "us-central1"
    launch_time = "2025-02-18T10:20:00Z"    # ← Already a string

    name_tag = "gcp-postgres-demo"
    utilization = 0.10
    cost = 0.0

    instance_data = {
        "resource_id": "gcp-sql-01",
        "name": name_tag,
        "type": instance_type,
        "status": state.lower(),
        "utilization": utilization,
        "monthly_cost": cost,
        "region": region,
        "provider": "GCP",
        "is_optimized": True,
        "last_activity": launch_time,        # ← Use string directly
        "creation_date": launch_time,        # ← No .isoformat()
        "recommendations": [
           
        ],
        "commands": [
            
        ]
    }

    # Save to DynamoDB for persistence
    save_resource_in_db(
        resource_id="gcp-sql-01",
        resource_type="CloudSQL",
        resource_data=instance_data
    )

    return [instance_data]
