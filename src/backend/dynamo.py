import boto3, os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

dynamodb = boto3.client(
    "dynamodb",
    region_name=os.getenv("AWS_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)
def save_recommendation(resource_id, resource_type, recommendation_text, metrics_snapshot,status='new'):
    from datetime import datetime

    item = {
        'resource_id': resource_id,
        'resource_type': resource_type,
        'recommendation_text': recommendation_text,
        'metrics_snapshot': metrics_snapshot,
        'last_checked_time': datetime.utcnow().isoformat(),
        'status': 'new',
        'cooldown_seconds': 86400  # Default 1 day cooldown
    }

    recommendations_table.put_item(Item=item)
    return item
def get_recommendation(resource_id, resource_type):
    response = recommendations_table.get_item(
        Key={
            'resource_id': resource_id,
            'resource_type': resource_type
        }
    )
    return response.get('Item')
def update_recommendation_status(resource_id, resource_type, new_status):
    response = recommendations.update_item(
        Key={
            'resource_id': resource_id,
            'resource_type': resource_type
        },
        UpdateExpression="set #s = :val",
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':val': new_status},
        ReturnValues="UPDATED_NEW"
    )
    return response

def is_in_cooldown(item):
    """Check if the resource is still within cooldown period."""
    if not item or 'last_checked_time' not in item:
        return False

    last_time = datetime.fromisoformat(item['last_checked_time'])
    cooldown = timedelta(seconds=item.get('cooldown_seconds', 86400))
    return datetime.utcnow() < last_time + cooldown

print(dynamodb.list_tables())
