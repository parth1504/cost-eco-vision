import overview
from fastapi import APIRouter

router = APIRouter(prefix="/resources", tags=["resources"])

@router.get("")
async def get_overview():
    overview_data = await overview.get_all_overview_data() 
    return {"data": overview_data}