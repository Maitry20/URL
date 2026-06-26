import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)

class Settings:
    # App Config
    APP_NAME: str = "URL Shortener API"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    
    # MySQL Database Config
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB: str = os.getenv("MYSQL_DB", "url_shortener")
    
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"

    # Redis Config
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # AWS DynamoDB Config
    # If AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY is empty, boto3 will attempt to use local IAM role / credentials
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    DYNAMODB_TABLE: str = os.getenv("DYNAMODB_TABLE", "users")
    # For local DynamoDB testing (e.g. LocalStack or local DynamoDB)
    DYNAMODB_ENDPOINT_URL: str = os.getenv("DYNAMODB_ENDPOINT_URL", "")
    
    # Local Network IP (for local mobile device testing/scanning)
    LOCAL_IP: str = os.getenv("LOCAL_IP", "")

    # JWT Config
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super_secret_jwt_signing_key_change_me_in_production_12345")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24)) # default 24 hours

settings = Settings()
