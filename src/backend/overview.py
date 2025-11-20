"""
Overview data for the ITOps dashboard
"""

# Mock overview data structure
mock_savings_data = {
    "monthly": 1234,
    "yearly": 14808,
    "co2Reduced": 2.4,
    "totalOptimizations": 23,
    "chartData": [
        {"month": "Jul", "savings": 800},
        {"month": "Aug", "savings": 950},
        {"month": "Sep", "savings": 1100},
        {"month": "Oct", "savings": 1050},
        {"month": "Nov", "savings": 1300},
        {"month": "Dec", "savings": 1234}
    ]
}

mock_activities = [
    {
        "id": "act-1",
        "action": "EC2 instance i-abc123 stopped",
        "resource": "web-server-2",
        "savings": 42,
        "timestamp": "2024-01-15T14:30:00Z",
        "type": "Cost"
    },
    {
        "id": "act-2",
        "action": "Security group updated",
        "resource": "prod-db",
        "savings": 0,
        "timestamp": "2024-01-15T13:15:00Z",
        "type": "Security"
    },
    {
        "id": "act-3",
        "action": "S3 lifecycle policy applied",
        "resource": "backup-bucket",
        "savings": 89,
        "timestamp": "2024-01-15T12:00:00Z",
        "type": "Cost"
    }
]

mock_recommendations = [
    {
        "id": "rec-1",
        "resource": "web-server-1 (i-0123456789)",
        "resourceType": "EC2",
        "issue": "Low CPU utilization (15%)",
        "recommendation": "Right-size from t3.medium to t3.small",
        "estimatedSavings": 245,
        "impact": "High",
        "category": "Cost",
        "status": "Pending"
    },
    {
        "id": "rec-2",
        "resource": "prod-db",
        "resourceType": "RDS",
        "issue": "Publicly accessible database",
        "recommendation": "Remove public access and use VPC endpoints",
        "estimatedSavings": 0,
        "impact": "High",
        "category": "Security",
        "status": "Pending"
    },
    {
        "id": "rec-3",
        "resource": "backup-bucket",
        "resourceType": "S3",
        "issue": "Old data in Standard storage",
        "recommendation": "Move data older than 90 days to Glacier",
        "estimatedSavings": 156,
        "impact": "Medium",
        "category": "Cost",
        "status": "Pending"
    }
]

def get_all_overview_data():
    """
    Get all overview data
    """
    return {
        "savingsData": generate_savings_mock(1234),
        "activities": mock_activities,
        "recommendations": mock_recommendations
    }

import random

def generate_savings_mock(current_month_value=1234):
    # realistic downward/upward drift factors for past 5 months
    multipliers = [0.65, 0.72, 0.85, 0.92, 1.05, 1.00]  # Jul → Dec trend
    
    base = current_month_value
    months = ["Jul", "Aug", "Sep", "Oct", "Nov"]
    
    chartData = []
    for month, mult in zip(months, multipliers):
        value = round(base * mult + random.uniform(-30, 30), 2)
        chartData.append({"month": month, "savings": value})

    # Derived values
    monthly = current_month_value
    yearly = round(sum([m["savings"] for m in chartData]), 2)
    co2 = round((monthly / 500), 2)           # simple realistic CO2 formula
    optimizations = random.randint(18, 32)    # looks real, not constant

    return {
        "monthly": monthly,
        "yearly": yearly,
        "co2Reduced": co2,
        "totalOptimizations": optimizations,
        "chartData": chartData
    }