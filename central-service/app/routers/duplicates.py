from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import DuplicatePair, User
from ..schemas import DuplicatePairCreate, DuplicatePairOut, DuplicatePairResolve

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


@router.post("/", response_model=DuplicatePairOut)
def create_duplicate_pair(
    pair: DuplicatePairCreate,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("admin", "user")),
):
    db_pair = DuplicatePair(
        image_a_id=pair.image_a_id,
        image_b_id=pair.image_b_id,
        match_type=pair.match_type,
    )
    db.add(db_pair)
    db.commit()
    db.refresh(db_pair)
    return db_pair


@router.get("/", response_model=list[DuplicatePairOut])
def list_unresolved_duplicates(
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    return db.query(DuplicatePair).filter(DuplicatePair.resolved == False).all()


@router.patch("/{pair_id}/resolve", response_model=DuplicatePairOut)
def resolve_duplicate(
    pair_id: int,
    body: DuplicatePairResolve,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("admin", "user")),
):
    pair = db.query(DuplicatePair).filter(DuplicatePair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Duplicate pair not found")
    pair.resolved = True
    pair.resolution = body.resolution
    db.commit()
    db.refresh(pair)
    return pair
