from fastapi import APIRouter, Body, HTTPException
from services import alerts
router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
async def get_alerts():
    print("Fetching all alerts...")
    alerts_data = await alerts.get_all_alerts()
    return alerts_data


@router.get("/{alert_id}")
async def get_alert(alert_id: str):
    alert = await alerts.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.put("/{alert_id}")
async def update_alert(alert_id: str, payload: dict = Body(...)):
    print("Updating alert:", alert_id)

    status = payload.get("status")
    if not status:
        raise HTTPException(status_code=422, detail="Missing 'status' in request body")

    alert = await alerts.update_alert(alert_id, status)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return alert


@router.delete("/{alert_id}")
def delete_alert(alert_id: str):
    alert = alerts.delete_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert