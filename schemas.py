from pydantic import BaseModel, EmailStr, HttpUrl, Field
from typing import Optional
from datetime import datetime

# --- User Auth Schemas ---

class UserRegister(BaseModel):
    email: EmailStr = Field(..., description="User's unique email address")
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    password: str = Field(..., min_length=6, description="User's password (min 6 characters)")

class UserLogin(BaseModel):
    email: EmailStr = Field(...)
    password: str = Field(...)

class UserResponse(BaseModel):
    userId: str
    email: EmailStr
    name: str
    created_at: str

# --- JWT Token Schemas ---

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- URL Shortener Schemas ---

class URLCreate(BaseModel):
    url: HttpUrl = Field(..., description="The original long URL to shorten")
    custom_alias: Optional[str] = Field(None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$", description="Optional custom short code alias")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration date and time")

class URLResponse(BaseModel):
    id: int
    code: str
    original_url: str
    short_url: str
    created_by: str
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }
