from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from routes.alerts import router as alerts_router
from routes.overview import router as overview_router
from routes.optimization import router as optimization_router
from routes.resources import router as resource_router
from routes.notification import router as notification_router
from routes.security import router as security_router
from routes.incident import router as incident_router
from routes.drift import router as drift_router
from routes.leaderboard import router as leaderboard_router

app = FastAPI(title="Cloud Management API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Health check endpoint
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "Cloud Management API",
        # "agent_configured": agent_client.is_configured()
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        # "agent_status": "configured" if agent_client.is_configured() else "not_configured",
        # "agent_details": {
        #     "region": agent_client.aws_region if agent_client.is_configured() else None,
        #     "agent_id": agent_client.agent_id if agent_client.is_configured() else None
        # }
    }

# Resources endpoints
app.include_router(resource_router)

# Alerts endpoints
app.include_router(alerts_router)   

# Overview endpoint
app.include_router(overview_router)   

# Security endpoints
app.include_router(security_router)

# Incidents endpoints
app.include_router(incident_router)

# Drift endpoints
app.include_router(drift_router)

# Leaderboard endpoints
app.include_router(leaderboard_router)

# Optimization endpoints
app.include_router(optimization_router)

# Notification endpoints
app.include_router(notification_router)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
