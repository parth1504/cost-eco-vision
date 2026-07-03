from services import overview
from fastapi import APIRouter

router = APIRouter(prefix="/overview", tags=["overview"])

@router.get("")
async def get_overview():
    overview_data = await overview.get_all_overview_data() 
    return {"data": overview_data}