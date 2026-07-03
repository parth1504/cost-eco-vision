from fastapi import APIRouter
from services.leaderboard import get_leaderboard

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("")
def get_leaderboard_data():
    """Get gamified leaderboard data"""
    return get_leaderboard()