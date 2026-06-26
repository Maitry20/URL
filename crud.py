from datetime import datetime
from sqlalchemy.orm import Session
from models import ShortURL

def get_url_by_code(db: Session, code: str) -> ShortURL | None:
    """
    Queries MySQL for a ShortURL record by its 6-character alphanumeric code.
    """
    return db.query(ShortURL).filter(ShortURL.code == code).first()

def get_user_urls(db: Session, email: str) -> list[ShortURL]:
    """
    Queries MySQL for all ShortURL records created by a specific user email.
    Orders them by creation date descending.
    """
    return db.query(ShortURL).filter(ShortURL.created_by == email).order_by(ShortURL.created_at.desc()).all()

def create_short_url(db: Session, original_url: str, created_by: str, code: str, expires_at: datetime | None = None) -> ShortURL:
    """
    Creates a new ShortURL record in MySQL and commits it to the database.
    """
    db_url = ShortURL(
        code=code,
        original_url=original_url,
        created_by=created_by,
        expires_at=expires_at
    )
    db.add(db_url)
    db.commit()
    db.refresh(db_url)
    return db_url

def delete_short_url(db: Session, code: str) -> bool:
    """
    Deletes a ShortURL record from MySQL by its code.
    Returns True if found and deleted, False otherwise.
    """
    db_url = db.query(ShortURL).filter(ShortURL.code == code).first()
    if db_url:
        db.delete(db_url)
        db.commit()
        return True
    return False
