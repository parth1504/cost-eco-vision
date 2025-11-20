"""
Provider-aware Bedrock client with strict JSON prompting, parsing + retry, and safe fallback.
Drop this into your backend and import `call_bedrock_reco(user_json)` from other modules.

Features:
- Uses MODEL_ID and BEDROCK_REGION env vars
- Builds model-specific request bodies (Anthropic/Claude, Amazon Nova, Meta Llama)
- Strong, single-line JSON prompt and low-temperature generation
- Robust parsing heuristics to extract JSON from model output
- Retry loop with corrective instruction
- Safe DEFAULT_RECO fallback
- (Optional) sandbox runner commented-out (dangerous - only enable if you know the risks)

Note: this file intentionally avoids executing model-generated code by default. It prefers
text->JSON extraction heuristics and will fall back to a conservative recommendation.
"""

import os
import json
import re
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError
from recos import parse_all_recommendations


# === Configuration ===
MODEL_ID = os.getenv("BEDROCK_MODEL", "amazon.nova-micro-v1:0")
REGION = os.getenv("BEDROCK_REGION", "us-east-1")
# Optional fallback model id (used if primary fails with gating errors)
FALLBACK_MODEL_ID = os.getenv("BEDROCK_FALLBACK_MODEL", "meta.llama3-8b-instruct-v1:0")

# boto3 Bedrock runtime client
br = boto3.client("bedrock-runtime", region_name=REGION)

# Default conservative recommendation
DEFAULT_RECO: Dict[str, Any] = {
    "action": "resize",
    "target_type": "EC2",
    "target_size": None,
    "reason": "fallback_"
    "_data",
    "estimated_savings_usd": None,
    "confidence": 0.15,
}

# Strict prompt template that requests a single-line JSON object
STRICT_PROMPT_TEMPLATE = (
    "SYSTEM: You are a cloud optimization assistant. FOLLOW THESE RULES EXACTLY:\n"
    "1) Output EXACTLY one single-line valid JSON object and NOTHING else -- no code, no explanation.\n"
    "2) Schema (must match exactly):\n"
    "{"
    "\"action\":\"<resize|stop|schedule|monitor>\","  # note: kept readable to the model
    "\"target_type\":\"<EC2|RDS|S3|other>\"," 
    "\"target_size\":<string|null>,\n"
    "\"reason\":<string>,\n"
    "\"estimated_savings_usd\":<number|null>,\n"
    "\"confidence\":<number>\n"
    "}\n"
    "3) If input is incomplete, return a conservative recommendation (monitor).\n"
    "4) ONE LINE ONLY. No newlines, no markdown, no surrounding text.\n"
    "INPUT_JSON: {input_json}\n"
    "Produce the single-line JSON object NOW."
)

# --- Parsing heuristics ---

def _extract_first_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Try multiple heuristics to recover a JSON/dict from model output without executing code."""
    if not text:
        return None

    # 1) Look for the first {...} block (reasonable upper bound to avoid catastrophic matching)
    m = re.search(r"\{[\s\S]{1,2000}\}", text)
    if m:
        candidate = m.group(0)
        # Try JSON parse
        try:
            return json.loads(candidate)
        except Exception:
            # Try replacing single quotes
            try:
                return json.loads(candidate.replace("'", '"'))
            except Exception:
                # Try ast-like eval via limited parsing (avoid eval in production)
                try:
                    # Fallback: eval-like parsing using json loads on cleaned string
                    def _replace_key_val(m):
                        return f'"{m.group(1)}":"{m.group(2)}"'
                    cleaned = re.sub(r"([\w_]+)\s*:\s*'([^']*)'", _replace_key_val, candidate)
                    return json.loads(cleaned)
                except Exception:
                    pass

    # 2) Look for explicit variable assignments like output_json = {...}
    m2 = re.search(r"output_json\s*=\s*(\{[\s\S]{1,2000}\})", text)
    if m2:
        candidate = m2.group(1)
        try:
            return json.loads(candidate)
        except Exception:
            try:
                return json.loads(candidate.replace("'", '"'))
            except Exception:
                pass

    # 3) Look for return json.dumps({...}) patterns
    m3 = re.search(r"return\s+json\.dumps\(\s*(\{[\s\S]{1,2000}\})\s*\)", text)
    if m3:
        candidate = m3.group(1)
        try:
            return json.loads(candidate)
        except Exception:
            try:
                return json.loads(candidate.replace("'", '"'))
            except Exception:
                pass

    return None


# --- Model request builders ---

def _build_body_for_model(model_id: str, prompt_text: str) -> (Dict[str, Any], str):
    """Return (body, contentType) for different Bedrock model types.
    This keeps the client provider/model-aware and prevents schema errors.
    """
    # Anthropic/Claude (Messages API)
    if model_id.startswith("anthropic.") or "claude" in model_id:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "temperature": 0.0,
            "system": [{"type": "text", "text": prompt_text}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": ""}]}],
        }
        return body, "application/json"

    # Amazon Nova (text-generation)
    if model_id.startswith("amazon.nova-"):
        body = {
            "inputText": prompt_text,
            "textGenerationConfig": {"maxTokenCount": 300, "temperature": 0.0, "topP": 0.9},
        }
        return body, "application/json"

    # Meta Llama (prompt style)
    if model_id.startswith("meta.") or model_id.startswith("llama"):
        body = {"prompt": prompt_text, "temperature": 0.0, "max_gen_len": 120}
        return body, "application/json"

    # Generic fallback
    return {"inputText": prompt_text, "textGenerationConfig": {"maxTokenCount": 120, "temperature": 0.0}}, "application/json"


def _invoke_model_raw(model_id: str, body: Dict[str, Any], content_type: str) -> str:
    """Invoke Bedrock and return the raw text content (best-effort for multiple providers)."""
    resp = br.invoke_model(modelId=model_id, body=json.dumps(body), accept="application/json", contentType=content_type)
    payload = json.loads(resp["body"].read())
    print("Bedrock raw response payload:", payload)
    # Normalize output extraction for common shapes
    if isinstance(payload, dict):
        if "content" in payload and isinstance(payload["content"], list):
            # Anthropic-like
            return payload["content"][0].get("text", "")
        if "outputText" in payload:
            return payload.get("outputText", "")
        if "generation" in payload:
            gen = payload.get("generation")
            if isinstance(gen, str):
                return gen
            # Try common nested shapes
            if isinstance(gen, dict):
                return json.dumps(gen)
        # last resort: return full payload as string
    return json.dumps(payload)


# --- Public API: call_bedrock_reco(user_json) ---

def call_bedrock_json(user_json: Dict[str, Any], model_id: Optional[str] = None, max_retries: int = 2) -> Dict[str, Any]:
    """Generate a single recommendation dict for given user_json.

    Returns a dict matching the schema or DEFAULT_RECO on failure.
    """
    mid = model_id or MODEL_ID
    prompt = STRICT_PROMPT_TEMPLATE.replace("{input_json}", json.dumps(user_json))
    print("user input json:", user_json)
    # Build body for the target model
    body, ctype = _build_body_for_model(mid, prompt)

    for attempt in range(max_retries + 1):
        try:
            raw_text = _invoke_model_raw(mid, body, ctype)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            # If gated or not allowed, try fallback model once
            if attempt == 0 and FALLBACK_MODEL_ID and FALLBACK_MODEL_ID != mid:
                mid = FALLBACK_MODEL_ID
                body, ctype = _build_body_for_model(mid, prompt)
                continue
            # otherwise return default
            print(f"Bedrock model invocation failed with error code {code}: {e}")
            return DEFAULT_RECO
        print(f"Bedrock model raw output (attempt {attempt+1}):", raw_text)
        # Try to extract JSON using heuristics
        parsed = _extract_first_json_block(raw_text)
        print("extracted json: ",parsed)
        if parsed and isinstance(parsed, dict) and parsed.get("action"):
            # Normalize fields
            parsed.setdefault("confidence", 0.5)
            if parsed.get("estimated_savings_usd") is None:
                parsed["estimated_savings_usd"] = None
            return parsed

        # If not parsed, attempt a corrective retry: append short corrective instruction and retry
        prompt = prompt + " CORRECTIVE: Return ONLY the single-line JSON object and nothing else."
        body, ctype = _build_body_for_model(mid, prompt)
        time.sleep(0.35)

    # All retries exhausted -> fallback
    print("All retries exhausted, returning default recommendation.")
    return DEFAULT_RECO


# === Optional: sandbox runner (DANGEROUS) ===
# The following function is provided for completeness but is commented out by default.
# DO NOT enable unless you fully understand the security risks and run it inside an isolated container.

# import subprocess, tempfile, sys
# def run_code_in_sandbox(raw_code: str, user_json: dict, timeout_seconds: int = 2):
#     """
#     Extremely risky: runs model-generated code in a subprocess. Only use in tightly controlled sandbox.
#     """
#     wrapper = f"""
# import json,sys
# user_json = json.loads(sys.stdin.read())
# {raw_code}
# try:
#     if 'output_json' in globals():
#         print(json.dumps(output_json))
#     else:
#         print(json.dumps({json.dumps(DEFAULT_RECO)}))
# except Exception:
#     print(json.dumps({json.dumps(DEFAULT_RECO)}))
# """
#     with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
#         f.write(wrapper)
#         fname = f.name
#     proc = subprocess.Popen([sys.executable, fname], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={})
#     try:
#         stdout, stderr = proc.communicate(input=json.dumps(user_json).encode('utf-8'), timeout=timeout_seconds)
#     except subprocess.TimeoutExpired:
#         proc.kill(); stdout, stderr = proc.communicate()
#     try:
#         return json.loads(stdout.decode('utf-8').strip())
#     finally:
#         try: os.remove(fname)
#         except: pass

# === End of file ===
