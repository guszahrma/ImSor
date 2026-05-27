from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_role
from ..database import get_db
from ..models import User, Community, CommunityMember, CommunityGranter
from ..schemas import CommunityCreate, CommunityOut, CommunityMemberAdd, CommunityGranterAdd

router = APIRouter(prefix="/communities", tags=["communities"])


def _to_out(c: Community) -> dict:
    return {
        "id": c.id,
        "creator_id": c.creator_id,
        "name": c.name,
        "created_at": c.created_at,
        "member_ids": [m.user_id for m in c.members],
        "granter_ids": [g.user_id for g in c.granters],
    }


@router.get("/", response_model=list[CommunityOut])
def list_communities(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    return [_to_out(c) for c in db.query(Community).all()]


@router.post("/", response_model=CommunityOut)
def create_community(
    data: CommunityCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    c = Community(creator_id=data.creator_id, name=data.name)
    db.add(c)
    try:
        db.flush()
        # Auto-add creator as member and granter
        db.add(CommunityMember(community_id=c.id, user_id=data.creator_id))
        db.add(CommunityGranter(community_id=c.id, user_id=data.creator_id))
        db.commit()
        db.refresh(c)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Community already exists for this creator")
    return _to_out(c)


@router.delete("/{community_id}")
def delete_community(
    community_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    c = db.query(Community).filter(Community.id == community_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Community not found")
    db.delete(c)
    db.commit()
    return {"detail": "Deleted"}


# --- Members ---

@router.post("/{community_id}/members")
def add_member(
    community_id: int,
    data: CommunityMemberAdd,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    if not db.query(Community).filter(Community.id == community_id).first():
        raise HTTPException(status_code=404, detail="Community not found")
    m = CommunityMember(community_id=community_id, user_id=data.user_id)
    db.add(m)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Already a member")
    return {"detail": "Added"}


@router.delete("/{community_id}/members/{user_id}")
def remove_member(
    community_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    c = db.query(Community).filter(Community.id == community_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Community not found")
    if c.creator_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the creator from their own community")
    m = db.query(CommunityMember).filter_by(community_id=community_id, user_id=user_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(m)
    # Also revoke granter status if they had it
    g = db.query(CommunityGranter).filter_by(community_id=community_id, user_id=user_id).first()
    if g:
        db.delete(g)
    db.commit()
    return {"detail": "Removed"}


# --- Granters ---

@router.post("/{community_id}/granters")
def add_granter(
    community_id: int,
    data: CommunityGranterAdd,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    c = db.query(Community).filter(Community.id == community_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Community not found")
    is_member = db.query(CommunityMember).filter_by(
        community_id=community_id, user_id=data.user_id
    ).first()
    if not is_member:
        raise HTTPException(status_code=400, detail="User must be a member before they can be a granter")
    g = CommunityGranter(community_id=community_id, user_id=data.user_id)
    db.add(g)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Already a granter")
    return {"detail": "Added"}


@router.delete("/{community_id}/granters/{user_id}")
def remove_granter(
    community_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    c = db.query(Community).filter(Community.id == community_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Community not found")
    if c.creator_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the creator from granters")
    g = db.query(CommunityGranter).filter_by(community_id=community_id, user_id=user_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Granter not found")
    db.delete(g)
    db.commit()
    return {"detail": "Removed"}
