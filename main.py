import secrets
import string
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager

from config import settings
from database import engine, Base, get_db
import schemas
import crud
import cache
import auth
import dynamo
import models

# Alphanumeric character set for short code generation
CODE_CHARACTERS = string.ascii_letters + string.digits

def generate_short_code(db: Session) -> str:
    """
    Generates a unique 6-character alphanumeric code.
    Retries up to 5 times if a collision occurs.
    """
    for _ in range(5):
        code = "".join(secrets.choice(CODE_CHARACTERS) for _ in range(6))
        # Check collision in MySQL
        if not crud.get_url_by_code(db, code):
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate a unique short code. Please try again."
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    print("Initializing services...")
    
    # 1. Auto-create MySQL tables
    try:
        Base.metadata.create_all(bind=engine)
        print("MySQL tables verified/created successfully.")
    except Exception as e:
        print(f"Error initializing MySQL tables: {e}")
        print("Continuing startup. MySQL connection will retry on request.")

    # 2. Auto-create AWS DynamoDB table
    try:
        dynamo.init_dynamodb()
    except Exception as e:
        print(f"Error initializing DynamoDB: {e}")
        print("Continuing startup. Ensure DynamoDB (or LocalStack) is running if registration/login is used.")

    yield
    # Shutdown actions (if any)
    print("Shutting down services...")

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Enable CORS for local development (important if opening frontend files directly via file://)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Authentication Endpoints ---

@app.post("/auth/register", response_model=schemas.Token)
def register(user_in: schemas.UserRegister):
    """
    Registers a new user. Hashes the password and stores the profile in DynamoDB.
    Returns a JWT access token upon successful registration.
    """
    # Hash the password
    hashed_password = auth.get_password_hash(user_in.password)
    
    # Save to DynamoDB
    user = dynamo.create_user(
        email=user_in.email.lower(),
        name=user_in.name,
        hashed_password=hashed_password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email is already registered."
        )
        
    # Generate JWT token
    access_token = auth.create_access_token(data={"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin):
    """
    Authenticates a user using credentials stored in DynamoDB.
    Returns a JWT access token upon successful verification.
    """
    # Fetch user from DynamoDB
    user = dynamo.get_user_by_email(credentials.email.lower())
    
    if not user or not auth.verify_password(credentials.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Generate JWT token
    access_token = auth.create_access_token(data={"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

# --- URL Shortening Endpoints ---

@app.post("/shorten")
def shorten_url(
    payload: schemas.URLCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(auth.get_current_user)
):
    """
    Protected route. Accepts a long URL, generates a 6-character short code,
    stores it in MySQL, and returns the shortened URL.
    """
    original_url = str(payload.url)
    
    # Generate unique 6-char code
    code = generate_short_code(db)
    
    # Save to MySQL
    short_url_obj = crud.create_short_url(
        db=db,
        original_url=original_url,
        created_by=current_user["email"],
        code=code
    )
    
    # Construct base URL dynamically or fallback to localhost:8000
    base_url = str(request.base_url)
    # Ensure it ends with a slash, or strip trailing slash if needed
    if base_url.endswith("/"):
        base_url = base_url[:-1]
        
    short_url = f"{base_url}/{short_url_obj.code}"
    
    return {
        "id": short_url_obj.id,
        "code": short_url_obj.code,
        "original_url": short_url_obj.original_url,
        "short_url": short_url,
        "created_by": short_url_obj.created_by,
        "created_at": short_url_obj.created_at
    }

@app.get("/my/urls")
def get_my_urls(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(auth.get_current_user)
):
    """
    Protected route. Returns all short URLs created by the currently logged-in user.
    """
    db_urls = crud.get_user_urls(db, current_user["email"])
    
    # Format URLs with the correct domain/port
    base_url = str(request.base_url)
    if base_url.endswith("/"):
        base_url = base_url[:-1]
        
    response_urls = []
    for db_url in db_urls:
        response_urls.append({
            "id": db_url.id,
            "code": db_url.code,
            "original_url": db_url.original_url,
            "short_url": f"{base_url}/{db_url.code}",
            "created_by": db_url.created_by,
            "created_at": db_url.created_at
        })
        
    return response_urls

# --- Redirection Endpoint (Public) ---

@app.get("/{code}")
def redirect_to_url(code: str, db: Session = Depends(get_db)):
    """
    Public redirection route. Implements Cache-Aside pattern:
    1. Checks Redis first for the short code.
    2. If found (Cache Hit), redirects immediately.
    3. If not found (Cache Miss), queries MySQL.
    4. If found in MySQL, caches the mapping in Redis with a 1-hour TTL and redirects.
    5. If not found, returns a 404 error.
    """
    # 1. Check Redis Cache
    cached_url = cache.get_cached_url(code)
    if cached_url:
        print(f"[Cache-Aside] Cache HIT for code '{code}'. Redirecting to: {cached_url}")
        return RedirectResponse(url=cached_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        
    # 2. Cache Miss - Query MySQL Database
    print(f"[Cache-Aside] Cache MISS for code '{code}'. Querying MySQL...")
    db_url = crud.get_url_by_code(db, code)
    if not db_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The shortened URL code was not found or has expired."
        )
        
    # 3. Save to Redis Cache (TTL = 1 hour / 3600 seconds)
    print(f"[Cache-Aside] Saving code '{code}' to Redis cache.")
    cache.set_cached_url(code, db_url.original_url, ttl=3600)
    
    # 4. Redirect to the original long URL
    return RedirectResponse(url=db_url.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

# --- Frontend Serving Routes (Convenience) ---

@app.get("/")
def read_root():
    return FileResponse("index.html")

@app.get("/index.html")
def read_index():
    return FileResponse("index.html")

@app.get("/register.html")
def read_register():
    return FileResponse("register.html")

@app.get("/login.html")
def read_login():
    return FileResponse("login.html")

@app.get("/dashboard.html")
def read_dashboard():
    return FileResponse("dashboard.html")
