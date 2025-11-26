from typing import List, Dict, Any

mock_optimization_config = {
    "idle_resources_enabled": True,
    "right_sizing_level": 70,
    "scheduling_enabled": False,
    "auto_scaling_level": 50,
    "storage_optimization_enabled": True
}

mock_optimization_recommendations: List[Dict[str, Any]] = [
    {
        "id": "opt-1",
        "category": "Idle Resources",
        "title": "Stop Idle EC2 Instances",
        "description": "3 EC2 instances have been running with <5% CPU utilization for over 7 days",
        "estimated_savings": 245,
        "impact": "High",
        "resources": ["i-0123456789", "i-abcdef1234", "i-xyz9876543"],
        "status": "Pending"
    },
    {
        "id": "opt-2",
        "category": "Right-sizing",
        "title": "Downsize Oversized Instances",
        "description": "Right-size instances from t3.large to t3.medium based on usage patterns",
        "estimated_savings": 400,
        "impact": "High",
        "resources": ["web-server-1", "api-server-2"],
        "status": "Pending"
    },
    {
        "id": "opt-3",
        "category": "Scheduling",
        "title": "Enable Dev/Test Scheduling",
        "description": "Stop dev/test resources during non-business hours (6 PM - 8 AM)",
        "estimated_savings": 156,
        "impact": "Medium",
        "resources": ["dev-server-1", "test-db"],
        "status": "Pending"
    },
    {
        "id": "opt-4",
        "category": "Storage",
        "title": "Archive Old S3 Data",
        "description": "Move data older than 90 days to Glacier storage class",
        "estimated_savings": 89,
        "impact": "Medium",
        "resources": ["backup-bucket", "logs-bucket"],
        "status": "Pending"
    }
]

def calculate_savings(config: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate projected savings based on configuration"""
    monthly_savings = 0
    co2_reduction = 0
    
    if config.get("idle_resources_enabled", False):
        monthly_savings += 245
        co2_reduction += 0.8
    
    right_sizing = config.get("right_sizing_level", 0)
    monthly_savings += (right_sizing / 100) * 400
    co2_reduction += (right_sizing / 100) * 1.2
    
    if config.get("scheduling_enabled", False):
        monthly_savings += 156
        co2_reduction += 0.5
    
    auto_scaling = config.get("auto_scaling_level", 0)
    monthly_savings += (auto_scaling / 100) * 300
    co2_reduction += (auto_scaling / 100) * 0.9
    
    if config.get("storage_optimization_enabled", False):
        monthly_savings += 89
        co2_reduction += 0.3
    
    return {
        "monthly": round(monthly_savings),
        "yearly": round(monthly_savings * 12),
        "co2_reduction": round(co2_reduction * 10) / 10,
        "optimization_score": min(95, round((monthly_savings / 1190) * 100))
    }

def get_optimization_data():
    """Get all optimization data including config, recommendations, and projections"""
    return {
        "config": mock_optimization_config,
        "recommendations": mock_optimization_recommendations,
        "projections": calculate_savings(mock_optimization_config)
    }

def update_optimization_config(config: Dict[str, Any]):
    """Update optimization configuration"""
    global mock_optimization_config
    mock_optimization_config.update(config)
    return {
        "config": mock_optimization_config,
        "projections": calculate_savings(mock_optimization_config)
    }

def apply_optimization(optimization_id: str):
    """Apply a specific optimization recommendation"""
    for opt in mock_optimization_recommendations:
        if opt["id"] == optimization_id:
            opt["status"] = "Applied"
            return {
                "success": True,
                "optimization": opt,
                "message": f"Successfully applied optimization: {opt['title']}"
            }
    return {
        "success": False,
        "message": "Optimization not found"
    }
