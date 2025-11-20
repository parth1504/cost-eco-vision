import json
import re

# --- Default safety recommendation ---
DEFAULT_RECO = {
    "action": "resize",
    "target_type": None,
    "target_size": None,
    "reason": "insufficient_data",
    "estimated_savings_usd": None,
    "confidence": 0.2,
    "cli_command": None,
}

# --------- 1) Extract JSON from noisy LLM payload ---------
def extract_json_from_payload(payload_text: str):
    """
    Extracts the FIRST JSON object from messy Bedrock output.
    Works even if model includes commentary, markdown, timestamps, or code.
    """

    # Find any {...} JSON-like substring (limited to avoid runaway match)
    print("Extracting JSON from payload:", payload_text)
    m = re.search(r"\{[\s\S]{1,800}\}", payload_text)
    if not m:
        return None

    text = m.group(0).strip()

    # Try parsing directly
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try replacing single quotes (LLMs often mix them)
    try:
        return json.loads(text.replace("'", '"'))
    except Exception:
        pass

    return None  # failed to parse


# --------- 2) Attach AWS CLI command logic ---------

def attach_cli_command(reco: dict, resource_id: str):
    print("Attaching CLI command for resource:", reco)
    print("Resource ID:", resource_id)
    action = reco.get("action")
    rtype = reco.get("target_type")
    tsize = reco.get("target_size")

    # --- EC2 ---
    if rtype == "EC2":
        if action == "stop":
            reco["cli_command"] = f"aws ec2 stop-instances --instance-ids {resource_id}"

        elif action == "resize" and tsize:
            reco["cli_command"] = (
                f"aws ec2 modify-instance-attribute "
                f"--instance-id {resource_id} "
                f"--instance-type \"Value={tsize}\""
            )

        elif action == "schedule":
            reco["cli_command"] = (
                f"# Example scheduled stop using EventBridge\n"
                f"aws events put-rule --schedule-expression 'cron(0 20 * * ? *)' --name StopEC2Daily\n"
                f"aws events put-targets --rule StopEC2Daily --targets Id=1,Arn=<lambda-arn>"
            )

        else:
            reco["cli_command"] = None

    # --- S3 ---
    elif rtype == "S3":
        if action == "schedule":
            reco["cli_command"] = (
                f"aws s3api put-bucket-lifecycle-configuration "
                f"--bucket {resource_id} "
                f"--lifecycle-configuration 'file://lifecycle.json'"
            )
        else:
            reco["cli_command"] = None

    # --- DynamoDB ---
    elif rtype == "DynamoDB":
        if action == "resize" and tsize:
            reco["cli_command"] = (
                f"aws dynamodb update-table "
                f"--table-name {resource_id} "
                f"--provisioned-throughput ReadCapacityUnits={tsize},WriteCapacityUnits={tsize}"
            )
        else:
            reco["cli_command"] = None

    return reco


# --------- 3) Parse multiple payloads ---------

def parse_all_recommendations(raw_payloads: list, resource_ids: list):
    """
    raw_payloads: list of 'Bedrock raw response payload' strings
    resource_ids: matching list of resource names (EC2 ID, S3 bucket, DynamoDB table)
    """

    final_results = []

    for raw, res_id in zip(raw_payloads, resource_ids):
        # Extract the JSON part
        json_obj = extract_json_from_payload(raw)

        # If JSON missing → use default
        if not json_obj:
            reco = DEFAULT_RECO.copy()
        else:
            reco = DEFAULT_RECO.copy()
            reco.update(json_obj)

        # Attach AWS CLI command
        reco = attach_cli_command(reco, res_id)

        # Wrap with resource ID
        final_results.append({
            "resource": res_id,
            "recommendation": reco
        })

    return final_results
