"""
Push local application logs to CloudWatch for testing the Engineering Intelligence
system without deploying to EC2.

Usage:
    python push_logs_to_cloudwatch.py --log-group /app/order-processing-api --region us-east-1

Reads from the running local app's stdout or from a log file,
and streams to CloudWatch Logs in real-time.
"""

import argparse
import os
import subprocess
import sys
import time

import boto3


def create_log_stream(client, log_group: str, stream_name: str):
    try:
        client.create_log_group(logGroupName=log_group)
    except client.exceptions.ResourceAlreadyExistsException:
        pass

    try:
        client.create_log_stream(logGroupName=log_group, logStreamName=stream_name)
    except client.exceptions.ResourceAlreadyExistsException:
        pass


def push_logs(log_group: str, region: str, stream_name: str):
    client = boto3.client("logs", region_name=region)
    create_log_stream(client, log_group, stream_name)

    sequence_token = None
    batch = []
    last_flush = time.time()

    print(f"Streaming logs to {log_group}/{stream_name}")
    print("Reading from stdin (pipe your app logs here)...")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        batch.append({
            "timestamp": int(time.time() * 1000),
            "message": line,
        })

        if len(batch) >= 20 or (time.time() - last_flush) > 5:
            params = {
                "logGroupName": log_group,
                "logStreamName": stream_name,
                "logEvents": sorted(batch, key=lambda x: x["timestamp"]),
            }
            if sequence_token:
                params["sequenceToken"] = sequence_token

            try:
                resp = client.put_log_events(**params)
                sequence_token = resp.get("nextSequenceToken")
                print(f"  Pushed {len(batch)} events")
            except Exception as e:
                print(f"  Error pushing logs: {e}")

            batch = []
            last_flush = time.time()

    # Flush remaining
    if batch:
        params = {
            "logGroupName": log_group,
            "logStreamName": stream_name,
            "logEvents": sorted(batch, key=lambda x: x["timestamp"]),
        }
        if sequence_token:
            params["sequenceToken"] = sequence_token
        try:
            client.put_log_events(**params)
            print(f"  Final flush: {len(batch)} events")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push logs to CloudWatch")
    parser.add_argument("--log-group", default="/app/order-processing-api")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--stream", default=f"local-dev/{int(time.time())}")
    args = parser.parse_args()

    push_logs(args.log_group, args.region, args.stream)
