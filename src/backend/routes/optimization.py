from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any

from . import optimization
# import agent_client
# import agent_logic

router = APIRouter(prefix="/optimization", tags=["optimization"])

# @router.get("")
# def get_optimization(use_agent: bool = Query(False, description="Enable AI-driven insights via AWS Strands Agent")):
#     optimization_data = optimization.get_optimization_data()
    
#     if use_agent and agent_client.is_configured():
#         prompt = agent_logic.format_optimization_prompt(optimization_data)
#         agent_response = agent_client.invoke_agent(prompt)
#         processed_response = agent_logic.process_agent_response(agent_response, "optimization")
        
#         return {
#             **optimization_data,
#             "agent_insights": processed_response
#         }
    
#     return optimization_data


# @router.post("/config")
# def update_optimization(config: Dict[str, Any]):
#     return optimization.update_optimization_config(config)


# @router.post("/apply")
# def apply_optimization_action(optimization_id: str):
#     result = optimization.apply_optimization(optimization_id)
#     if not result.get("success"):
#         raise HTTPException(status_code=404, detail=result.get("message"))
#     return result