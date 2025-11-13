# agent/recommendation_agent.py
from typing import Dict
from dynamo import save_recommendation, get_recommendation, is_in_cooldown
from bedrock_client import call_bedrock_json  # your thin wrapper returning dict

SYSTEM = (
 "You are a cloud optimization assistant. "
 "Given instance metrics, return JSON: "
 "{action:'stop|resize|schedule|none', target_type?:string, reason:string, risk:'low|med|high', short:'one-line'}"
)

async def generate_recommendation(instance: Dict) -> Dict:
    payload = {
        "id": instance["id"],
        "type": instance.get("type","EC2"),
        "cpu_avg": instance.get("cpu_avg"),
        "net_in": instance.get("network_in"),
        "net_out": instance.get("network_out"),
        "cost_month": instance.get("cost"),
        "instance_type": instance.get("instance_type"),
    }
    return call_bedrock_json(system=SYSTEM, user_json=payload)

def upsert_recommendation(instance: Dict) -> Dict:
    rid = instance["id"]; rtype = instance.get("type","EC2")
    existing = get_recommendation(rid, rtype)
    if is_in_cooldown(existing):
        return existing
    reco = generate_recommendation(instance)
    save_recommendation(rid, rtype, reco, instance)
    return reco
