from datetime import datetime
from typing import List, Dict, Any
from resources import get_all_resources   # <-- Your existing resources API
from dynamo import save_resource_in_db, get_resource_from_db
from decimal import Decimal
from fastapi import HTTPException

def decimal_to_float(obj):
    """Convert DynamoDB Decimal types → float safely."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    return obj

async def generate_alerts_from_resources() -> List[Dict[str, Any]]:
    """Generate alerts dynamically based on each resource's recommendations."""
    alerts = []
    
    resources = await get_all_resources()   # fetch EC2 + S3 + Dynamo + others
    print(f"Generating alerts from {len(resources)} resources")
    for resource in resources:
        resource_id = resource.get("resource_id")
        recs = resource.get("recommendations", [])

        for rec in recs:
            alert = {
                "id": f"{resource_id}:{rec.get('title').replace(' ', '~')}",
                "title": rec.get("title"),
                "message": rec.get("issue"),               # one-line issue
                "severity": rec.get("severity").capitalize(),
                "source": rec.get("type").capitalize(),    # cost / security / performance
                "affected_resources": [resource_id],
                "status": "active",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "impact": rec.get("impact", "medium"),
                "saving": rec.get("saving", "N/A"),
                "resource_type": resource.get("type"),
                "region": resource.get("region"),
            }

            alerts.append(alert)

    return alerts


async def get_all_alerts() -> List[Dict[str, Any]]:
    """Return dynamically computed alerts (no mock data).""" 
    return await generate_alerts_from_resources()


async def get_alert_by_id(alert_id: str):
    """Fetch a single alert from dynamic generation."""
    alerts = await generate_alerts_from_resources()
    return next((a for a in alerts if a["id"] == alert_id), None)


async def update_alert(alert_id: str, new_status: str):
    """
    Update alert status by mapping it to the correct resource + recommendation.
    alert_id format: <resource_id>-<title-with-dashes>
    """

    # -----------------------------
    # 1. Parse alert_id
    # -----------------------------
    try:
        parts = alert_id.split(":", 1)
        resource_id = parts[0]
        rec_title_raw = parts[1].replace("~", " ")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid alert ID format")

    # -----------------------------
    # 2. Find resource (try all resource types)
    # -----------------------------
    resource_types = ["EC2", "S3", "DynamoDB"]
    resource = None
    resource_type_found = None

    for r_type in resource_types:
        r = get_resource_from_db(resource_id, r_type)
        if r:
            resource = r
            resource_type_found = r_type
            break

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found for this alert")

    # -----------------------------
    # 3. Find correct recommendation inside resource
    # -----------------------------
    rec_list = resource.get("recommendations", [])
    target_rec = None

    for rec in rec_list:
        if rec.get("title", "").lower() == rec_title_raw.lower():
            target_rec = rec
            break

    if not target_rec:
        raise HTTPException(status_code=404, detail="Recommendation not found in resource")

    # -----------------------------
    # 4. Update recommendation status
    # -----------------------------
    target_rec["status"] = new_status.lower()  

    # -----------------------------
    # 5. Save updated resource
    # -----------------------------
    save_resource_in_db(
        resource_id=resource_id,
        resource_type=resource_type_found,
        resource_data=resource
    )

    # -----------------------------
    # 6. Return updated resource cleaned for frontend
    # -----------------------------
    return decimal_to_float(resource)


async def delete_alert(alert_id: str):
    """
    Alerts are recreated each time, so delete is virtual.
    If needed, implement a suppression list stored in DynamoDB.
    """
    return {
        "id": alert_id,
        "status": "suppressed",
        "message": "Alert suppressed until next refresh cycle."
    }
