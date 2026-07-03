# Mock data for Gamified Leaderboard

mock_leaderboard_entries = [
    {
        "id": "team-1",
        "team": "Platform Team",
        "user": "Pranali Shinde",
        "savings": 28,
        "optimizations": 3,
        "rank": 1
    },
    {
        "id": "team-2",
        "team": "Devops",
        "user": "Parth Shah",
        "savings": 21,
        "optimizations": 2,
        "rank": 2
    },
    {
        "id": "team-3",
        "team": "SRE",
        "user": "Vedant Kadam",
        "savings": 19,
        "optimizations": 2,
        "rank": 3
    },
    {
        "id": "team-4",
        "team": "Integrations",
        "user": "Aarav Joshi",
        "savings": 6,
        "optimizations": 1,
        "rank": 4
    }
]

def get_leaderboard():
    """Return leaderboard data"""
    return {
        "leaderboard": mock_leaderboard_entries,
        "totalSavings": sum(entry["savings"] for entry in mock_leaderboard_entries)
    }
