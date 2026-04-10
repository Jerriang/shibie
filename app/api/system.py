from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True, "time": datetime.now(UTC).isoformat(), "db": "up"}
