import os
import boto3
from dotenv import load_dotenv

load_dotenv()

def get_session():
    return boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "eu-north-1")
    )

def get_client(service: str):
    return get_session().client(service)

def get_resource(service: str):
    return get_session().resource(service)

def get_region():
    return os.getenv("AWS_DEFAULT_REGION", "eu-north-1")
