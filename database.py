from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# Pass ssl connection arguments if connecting to a secure cloud database (e.g. Aiven)
connect_args = {}
if "aivencloud.com" in settings.DATABASE_URL or "tidbcloud.com" in settings.DATABASE_URL:
    connect_args["ssl"] = {}

# Create engine using PyMySQL driver
# pool_pre_ping checks connection liveness on checkout
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args=connect_args
)

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base class for models
Base = declarative_base()

# Database session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
