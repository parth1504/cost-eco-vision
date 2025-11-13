# bedrock_client.py
import os, json, boto3
from botocore.exceptions import ClientError

MODEL_ID = os.getenv("BEDROCK_MODEL", "meta.llama3-8b-instruct-v1:0")  # or amazon.nova-micro-v1:0 or anthropic...

REGION = os.getenv("BEDROCK_REGION", "us-east-1")
br = boto3.client("bedrock-runtime", region_name=REGION)

def _body_for_model(model_id: str, system: str, user_json: dict):
    # text_in = (
    #     f"{system}\n\n"
    #     "Return ONLY JSON. If unsure, use {\"action\":\"none\",\"reason\":\"insufficient_data\"}.\n"
    #     f"INPUT_JSON:\n{json.dumps(user_json)}"
    # )
    text_in = """{system}\n\n You are a cloud infrastructure optimization assistant. 
        OUTPUT RULES (read carefully):
        1) Output EXACTLY one valid JSON object and nothing else — no code, no backticks, no explanation, no surrounding text.
        2) The JSON must follow this exact schema:
        {
        "action": "<resize|stop|schedule|monitor>",
        "target_type": "<EC2|RDS|S3|other>",
        "target_size": "<optional string, e.g. t3.small (required only for resize)>",
        "reason": "<short reason in 5-12 words>",
        "estimated_savings_usd": <number or null>,
        "confidence": <float 0.0-1.0>
        }
        3) ALWAYS return a recommendation. If input is incomplete or ambiguous, choose a conservative recommendation (prefer 'monitor' or 'resize' to a single smaller size) rather than returning no action.
        4) Keep values short. 'reason' must be plain text (no JSON inside). 'confidence' should reflect model certainty (0.0 low — 1.0 high).
        5) Do NOT output code, markdown, or any explanation. Only the JSON object.

        INPUT (JSON):
        {user_json}

        Produce the JSON object now."""

    if model_id.startswith("anthropic."):
        # Claude 3 – Messages API
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "temperature": 0.2,
            "system": [{"type": "text", "text": system + "\nReturn ONLY JSON."}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": json.dumps(user_json)}]}],
        }, "application/json"

    if model_id.startswith("meta."):
        # Llama 3 – prompt schema
        return {
            "prompt": text_in,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_gen_len": 300
        }, "application/json"

    if model_id.startswith("amazon.nova-"):
        # Nova text – inputText + textGenerationConfig
        return {
            "inputText": text_in,
            "textGenerationConfig": {
                "maxTokenCount": 300,
                "temperature": 0.2,
                "topP": 0.9
            }
        }, "application/json"

    # Fallback: simple prompt
    return {"prompt": text_in, "max_gen_len": 300, "temperature": 0.2, "top_p": 0.9}, "application/json"


def _parse_output(model_id: str, payload: dict) -> str:
    if model_id.startswith("anthropic."):
        return payload["content"][0]["text"]
    if model_id.startswith("amazon.nova-"):
        # Nova returns {"outputText": "...", ...}
        return payload.get("outputText", "")
    # Meta & generic text-gen usually return "generation" or "completions" – Bedrock normalizes to "generation" for Llama
    return payload.get("generation") or payload.get("completions", [{}])[0].get("data", {}).get("text", "") or payload.get("outputText", "")


def call_bedrock_json(system: str, user_json: dict) -> dict:
    body, ctype = _body_for_model(MODEL_ID, system, user_json)
    try:
        resp = br.invoke_model(modelId=MODEL_ID, body=json.dumps(body), accept="application/json", contentType=ctype)
    except ClientError as e:
        raise

    payload = json.loads(resp["body"].read())
    text = _parse_output(MODEL_ID, payload)
    print("Bedrock raw output:", text)
    try:
        return json.loads(text)
    except Exception:
        print("Raisin error parsing Bedrock output as JSON")
        return {"action": "none", "reason": text[:500]}
