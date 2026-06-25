import boto3
from botocore.exceptions import ClientError
import uuid
from datetime import datetime, timezone
from config import settings

def get_dynamodb_resource():
    """
    Initializes and returns a boto3 DynamoDB resource.
    Supports credentials from environment variables or IAM roles.
    Uses custom endpoint URL if specified (useful for LocalStack / testing).
    """
    params = {}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        params['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
        params['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_REGION:
        params['region_name'] = settings.AWS_REGION
    if settings.DYNAMODB_ENDPOINT_URL:
        params['endpoint_url'] = settings.DYNAMODB_ENDPOINT_URL
    return boto3.resource('dynamodb', **params)

dynamodb = get_dynamodb_resource()

def init_dynamodb():
    """
    Checks if the users table exists in DynamoDB.
    If not, creates it with 'email' as the partition key.
    """
    table_name = settings.DYNAMODB_TABLE
    try:
        table = dynamodb.Table(table_name)
        # Triggers a network check to verify table exists
        table.table_status
        print(f"DynamoDB table '{table_name}' verified.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException' or "not found" in str(e).lower():
            print(f"DynamoDB table '{table_name}' not found. Creating table...")
            try:
                table = dynamodb.create_table(
                    TableName=table_name,
                    KeySchema=[
                        {
                            'AttributeName': 'email',
                            'KeyType': 'HASH'  # Partition Key
                        }
                    ],
                    AttributeDefinitions=[
                        {
                            'AttributeName': 'email',
                            'AttributeType': 'S'
                        }
                    ],
                    ProvisionedThroughput={
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                )
                # Wait until the table exists
                table.wait_until_exists()
                print(f"DynamoDB table '{table_name}' created successfully.")
            except Exception as ce:
                print(f"Error creating DynamoDB table: {ce}")
                raise ce
        else:
            print(f"DynamoDB client error: {e}")
            raise e

def create_user(email: str, name: str, hashed_password: str):
    """
    Creates a new user profile in DynamoDB.
    Uses ConditionalExpression to prevent overwriting existing email.
    """
    table = dynamodb.Table(settings.DYNAMODB_TABLE)
    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
    try:
        table.put_item(
            Item={
                'userId': user_id,
                'email': email,
                'name': name,
                'hashed_password': hashed_password,
                'created_at': created_at
            },
            ConditionExpression='attribute_not_exists(email)'
        )
        return {
            'userId': user_id,
            'email': email,
            'name': name,
            'created_at': created_at
        }
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # User already exists
            return None
        raise e

def get_user_by_email(email: str):
    """
    Retrieves user profile from DynamoDB by email.
    """
    table = dynamodb.Table(settings.DYNAMODB_TABLE)
    try:
        response = table.get_item(
            Key={
                'email': email
            }
        )
        return response.get('Item')
    except ClientError as e:
        print(f"Error retrieving user {email} from DynamoDB: {e}")
        return None
