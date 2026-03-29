from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..database import get_db
from ..models import User
from ..schemas import SetupRequest, UserOut

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status")
def setup_status(db: Session = Depends(get_db)):
    has_users = db.query(User).first() is not None
    return {"setup_complete": has_users}


@router.post("/", response_model=UserOut)
def run_setup(body: SetupRequest, db: Session = Depends(get_db)):
    if db.query(User).first() is not None:
        raise HTTPException(status_code=400, detail="Setup already completed")

    admin = User(
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role="admin",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin
