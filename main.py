import secrets
import string
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
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
        # Check and apply database schema migrations automatically
        with engine.connect() as conn:
            try:
                from sqlalchemy import text
                # Modify code column to support longer custom aliases
                conn.execute(text("ALTER TABLE short_urls MODIFY COLUMN code VARCHAR(50);"))
                # Add expires_at column if it does not exist
                conn.execute(text("ALTER TABLE short_urls ADD COLUMN expires_at DATETIME DEFAULT NULL;"))
                conn.commit()
                print("Database migration check completed: tables updated.")
            except Exception as migration_err:
                print(f"Non-fatal migration note (column may already be updated): {migration_err}")
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

RESERVED_PATHS = {
    "login", "register", "dashboard", "auth", "shorten", "my", "index.html", 
    "login.html", "register.html", "dashboard.html", "", "favicon.ico", 
    "static", "docs", "redoc", "openapi.json"
}

# --- URL Shortening Endpoints ---

@app.post("/shorten", response_model=schemas.URLResponse)
def shorten_url(
    payload: schemas.URLCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(auth.get_current_user)
):
    """
    Protected route. Accepts a long URL, generates or validates a custom short code alias,
    saves it in MySQL, and returns the shortened URL.
    """
    original_url = str(payload.url)
    
    # Check if custom alias is provided
    if payload.custom_alias:
        alias = payload.custom_alias.strip()
        # Verify reserved paths
        if alias.lower() in RESERVED_PATHS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This custom alias is a reserved system path."
            )
        # Check collision in MySQL
        if crud.get_url_by_code(db, alias):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This custom alias is already taken."
            )
        code = alias
    else:
        # Generate unique 6-char code
        code = generate_short_code(db)
        
    # Expiration date validation
    if payload.expires_at:
        if payload.expires_at.tzinfo is not None:
            now = datetime.now(timezone.utc)
        else:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            
        if payload.expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Expiration date must be in the future."
            )
    
    # Save to MySQL
    short_url_obj = crud.create_short_url(
        db=db,
        original_url=original_url,
        created_by=current_user["email"],
        code=code,
        expires_at=payload.expires_at
    )
    
    # Construct base URL dynamically or fallback to localhost:8000
    base_url = str(request.base_url)
    # Ensure it ends with a slash, or strip trailing slash if needed
    if base_url.endswith("/"):
        base_url = base_url[:-1]
        
    if settings.LOCAL_IP:
        base_url = base_url.replace("localhost", settings.LOCAL_IP).replace("127.0.0.1", settings.LOCAL_IP)
        
    short_url = f"{base_url}/{short_url_obj.code}"
    
    return {
        "id": short_url_obj.id,
        "code": short_url_obj.code,
        "original_url": short_url_obj.original_url,
        "short_url": short_url,
        "created_by": short_url_obj.created_by,
        "created_at": short_url_obj.created_at,
        "expires_at": short_url_obj.expires_at
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
        
    if settings.LOCAL_IP:
        base_url = base_url.replace("localhost", settings.LOCAL_IP).replace("127.0.0.1", settings.LOCAL_IP)
        
    response_urls = []
    for db_url in db_urls:
        response_urls.append({
            "id": db_url.id,
            "code": db_url.code,
            "original_url": db_url.original_url,
            "short_url": f"{base_url}/{db_url.code}",
            "created_by": db_url.created_by,
            "created_at": db_url.created_at,
            "expires_at": db_url.expires_at
        })
        
    return response_urls

@app.delete("/delete/{code}", status_code=status.HTTP_200_OK)
def delete_url(
    code: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(auth.get_current_user)
):
    """
    Protected route. Deletes a shortened URL from MySQL and evicts it from Redis cache.
    Ensures that the URL belongs to the currently logged-in user.
    """
    db_url = crud.get_url_by_code(db, code)
    if not db_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The shortened URL was not found."
        )
        
    if db_url.created_by != current_user["email"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this URL."
        )
        
    # Delete from MySQL
    crud.delete_short_url(db, code)
    
    # Evict from Redis cache
    cache.delete_cached_url(code)
    
    return {"detail": "URL deleted successfully."}

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

# --- Redirection Endpoint (Public) ---

@app.get("/{code}")
def redirect_to_url(code: str, db: Session = Depends(get_db)):
    """
    Public redirection route. Implements Cache-Aside pattern:
    1. Checks Redis first for the short code.
    2. If found (Cache Hit), redirects immediately.
    3. If not found (Cache Miss), queries MySQL.
    4. Checks link expiration, evicts expired items, and renders an expiration page if needed.
    5. Caches valid items in Redis with an optimized TTL (matching link expiry if set) and redirects.
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
        
    # 3. Check Expiration
    if db_url.expires_at:
        if db_url.expires_at.tzinfo is not None:
            now = datetime.now(timezone.utc)
        else:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            
        if db_url.expires_at <= now:
            print(f"[Link Expiry] Code '{code}' has expired (expired at {db_url.expires_at}). Returning 410 Gone.")
            # Evict from Redis cache just in case
            cache.delete_cached_url(code)
            
            # Return a beautiful glassmorphic HTML error page
            return HTMLResponse(
                content="""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>SnipLink - Link Expired</title>
                    <script src="https://cdn.tailwindcss.com"></script>
                    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
                    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
                    <style>body { font-family: 'Outfit', sans-serif; background-color: #030712; }</style>
                </head>
                <body class="text-slate-200 min-h-screen flex flex-col items-center justify-center relative p-6">
                    <div class="absolute top-[-20%] left-[-20%] w-[60vw] h-[60vw] rounded-full bg-indigo-950/10 blur-[130px] pointer-events-none"></div>
                    <div class="absolute bottom-[-20%] right-[-20%] w-[55vw] h-[55vw] rounded-full bg-purple-950/10 blur-[130px] pointer-events-none"></div>
                    
                    <div class="bg-slate-900/40 border border-slate-800/80 p-8 sm:p-10 rounded-3xl max-w-md w-full text-center backdrop-blur-md shadow-2xl relative">
                        <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-rose-500 to-amber-500 rounded-t-3xl"></div>
                        <div class="w-20 h-20 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-500 flex items-center justify-center mx-auto mb-6 text-3xl">
                            <i class="fa-solid fa-hourglass-end"></i>
                        </div>
                        <h1 class="text-2xl font-bold text-white mb-2 font-display">Link Has Expired</h1>
                        <p class="text-slate-400 text-sm font-light mb-6">The short link you are trying to access has reached its expiration date and is no longer available.</p>
                        <a href="/" class="inline-block px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-semibold text-sm transition-all">
                            Back to Home
                        </a>
                    </div>
                </body>
                </html>
                """,
                status_code=status.HTTP_410_GONE
            )
            
    # 4. Calculate Cache TTL
    ttl = 3600
    if db_url.expires_at:
        if db_url.expires_at.tzinfo is not None:
            now = datetime.now(timezone.utc)
        else:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
        remaining = int((db_url.expires_at - now).total_seconds())
        if remaining > 0:
            ttl = min(3600, remaining)
        else:
            # Re-check edge case where it just expired
            cache.delete_cached_url(code)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="The shortened URL code has expired."
            )
        
    # 5. Save to Redis Cache
    print(f"[Cache-Aside] Saving code '{code}' to Redis cache with TTL={ttl}s.")
    cache.set_cached_url(code, db_url.original_url, ttl=ttl)
    
    # 6. Redirect to the original long URL
    return RedirectResponse(url=db_url.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
