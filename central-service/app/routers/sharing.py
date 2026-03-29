from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import SharingPermission, User
from ..schemas import SharingPermissionCreate, SharingPermissionOut

router = APIRouter(prefix="/sharing", tags=["sharing"])


@router.post("/", response_model=SharingPermissionOut)
def set_sharing_permission(
    perm: SharingPermissionCreate,
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    existing = (
        db.query(SharingPermission)
        .filter(
            SharingPermission.image_id == perm.image_id,
            SharingPermission.user_id == perm.user_id,
        )
        .first()
    )
    if existing:
        existing.decision = perm.decision
        db.commit()
        db.refresh(existing)
        return existing

    db_perm = SharingPermission(**perm.model_dump())
    db.add(db_perm)
    db.commit()
    db.refresh(db_perm)
    return db_perm


@router.get("/", response_model=list[SharingPermissionOut])
def list_sharing_permissions(
    image_id: int | None = Query(None),
    user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    query = db.query(SharingPermission)
    if image_id is not None:
        query = query.filter(SharingPermission.image_id == image_id)
    if user_id is not None:
        query = query.filter(SharingPermission.user_id == user_id)
    return query.all()
