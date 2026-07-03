"""
Demo Scenario Routes
---------------------
Add these endpoints to your incident routes for hackathon demos.

Add to routes/incident.py:
    from services.demo_scenarios import generate_demo_scenario_alerts, get_available_scenarios
"""

# --- Add these imports at the top of routes/incident.py ---
# from services.enhanced_alerts import generate_demo_scenario_alerts, get_available_scenarios

# --- Add these routes BEFORE the /{incident_id} catch-all ---

"""
@router.get("/scenarios")
def list_scenarios():
    '''List available demo scenarios for the UI.'''
    return get_available_scenarios()


@router.post("/scenarios/{scenario_key}")
async def inject_scenario(scenario_key: str):
    '''
    Inject a demo scenario's alerts into the system and run correlation.
    Returns the resulting incidents — should show the alerts grouped
    into meaningful multi-alert incidents.
    '''
    from services.enhanced_alerts import generate_demo_scenario_alerts
    from connections.db import upsert_alert, set_alert_incident, upsert_incident
    from services.correlation import correlate_alerts
    from services.alerts import generate_alerts_from_resources

    # 1. Get real alerts
    real_alerts = await generate_alerts_from_resources()

    # 2. Generate scenario alerts
    scenario_alerts = generate_demo_scenario_alerts(scenario_key)
    if not scenario_alerts:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_key}' not found")

    # 3. Combine real + scenario alerts
    all_alerts = real_alerts + scenario_alerts

    # 4. Persist all alerts
    for a in all_alerts:
        if a.get("id"):
            upsert_alert({**a, "alert_id": a["id"]})

    # 5. Correlate
    incidents = correlate_alerts(all_alerts)

    # 6. Persist incidents
    for inc in incidents:
        upsert_incident(inc)
        for alert_id in inc.get("member_alert_ids", []):
            set_alert_incident(alert_id, inc["incident_id"])

    # 7. Return only incidents that contain scenario alerts
    scenario_alert_ids = {a["id"] for a in scenario_alerts}
    scenario_incidents = [
        inc for inc in incidents
        if any(aid in scenario_alert_ids for aid in inc.get("member_alert_ids", []))
    ]

    return {
        "scenario": scenario_key,
        "alerts_injected": len(scenario_alerts),
        "incidents_created": len(scenario_incidents),
        "incidents": scenario_incidents,
    }
"""