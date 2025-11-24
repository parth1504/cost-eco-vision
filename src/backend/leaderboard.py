# Mock data for Gamified Leaderboard

mock_leaderboard_entries = [
    {
        "id": "team-1",
        "team": "Platform Team",
        "user": "Pranali Shinde",
        "savings": 28,
        "optimizations": 12,
        "rank": 1
    },
    {
        "id": "team-2",
        "team": "Data Engineering",
        "user": "Parth Shah",
        "savings": 21,
        "optimizations": 8,
        "rank": 2
    },
    {
        "id": "team-3",
        "team": "Mobile Team",
        "user": "Elena Rodriguez",
        "savings": 19,
        "optimizations": 15,
        "rank": 3
    },
    {
        "id": "team-4",
        "team": "Web Frontend",
        "user": "David Kim",
        "savings": 16,
        "optimizations": 6,
        "rank": 4
    }
]

def get_leaderboard():
    """Return leaderboard data"""
    return {
        "leaderboard": mock_leaderboard_entries,
        "totalSavings": sum(entry["savings"] for entry in mock_leaderboard_entries)
    }
