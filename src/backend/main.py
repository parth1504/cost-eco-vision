from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
import alerts
import resources
import security
import optimization

app = FastAPI(title="Cloud Management API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Alerts endpoints
@app.get("/alerts")
def get_alerts():
    return alerts.get_all_alerts()

@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str):
    alert = alerts.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@app.put("/alerts/{alert_id}")
def update_alert(alert_id: str, updates: Dict[str, Any]):
    alert = alerts.update_alert(alert_id, updates)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str):
    alert = alerts.delete_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

# Resources endpoints
@app.get("/resources")
def get_resources():
    return resources.get_all_resources()

@app.get("/resources/{resource_id}")
def get_resource(resource_id: str):
    resource = resources.get_resource_by_id(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource

@app.put("/resources/{resource_id}/optimize")
def optimize_resource(resource_id: str):
    resource = resources.get_resource_by_id(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    # Apply optimization - reduce cost by 30%
    updated_resource = resources.update_resource(resource_id, {
        "status": "Optimized",
        "monthly_cost": round(resource["monthly_cost"] * 0.7, 2)
    })
    return updated_resource

# Security endpoints
@app.get("/security")
def get_security():
    return security.get_all_findings()

@app.get("/security/{finding_id}")
def get_security_finding(finding_id: str):
    finding = security.get_finding_by_id(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Security finding not found")
    return finding

@app.post("/security/update")
def update_security_finding(finding_id: str, updates: Dict[str, Any]):
    finding = security.update_finding(finding_id, updates)
    if not finding:
        raise HTTPException(status_code=404, detail="Security finding not found")
    return {"success": True, "finding": finding}

# Optimization endpoints
@app.get("/optimization")
def get_optimization():
    return optimization.get_optimization_data()

@app.post("/optimization/config")
def update_optimization(config: Dict[str, Any]):
    return optimization.update_optimization_config(config)

@app.post("/optimization/apply")
def apply_optimization_action(optimization_id: str):
    result = optimization.apply_optimization(optimization_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
