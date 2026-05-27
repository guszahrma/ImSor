from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import Annotation, User
from ..schemas import AnnotationCreate, AnnotationOut, AnnotationUpdate, ClusterVoteSubmit

router = APIRouter(prefix="/annotations", tags=["annotations"])


@router.post("/", response_model=AnnotationOut)

def create_annotation(
    annotation: AnnotationCreate,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    db_annotation = Annotation(**annotation.model_dump())
    db.add(db_annotation)
    db.commit()
    db.refresh(db_annotation)
    return db_annotation


@router.get("/", response_model=list[AnnotationOut])
def list_annotations(
    image_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    query = db.query(Annotation)
    if image_id is not None:
        query = query.filter(Annotation.image_id == image_id)
    return query.all()


@router.post("/batch-vote", response_model=list[AnnotationOut])
def submit_cluster_vote(
    vote: ClusterVoteSubmit,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    """
    Upsert a Cluster Vote — one duplicate_role annotation per image per annotator.
    Replaces any existing duplicate_role annotation this user has on each image.
    """
    saved = []
    for item in vote.votes:
        existing = db.query(Annotation).filter_by(
            image_id=item.image_id,
            user_id=vote.user_id,
            annotation_type="duplicate_role",
        ).first()
        if existing:
            existing.value = item.value
            db.flush()
            saved.append(existing)
        else:
            ann = Annotation(
                image_id=item.image_id,
                user_id=vote.user_id,
                annotation_type="duplicate_role",
                value=item.value,
                source="manual",
            )
            db.add(ann)
            db.flush()
            saved.append(ann)
    db.commit()
    for ann in saved:
        db.refresh(ann)
    return saved


@router.patch("/{annotation_id}", response_model=AnnotationOut)
def update_annotation(
    annotation_id: int,
    body: AnnotationUpdate,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    ann = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")
    if body.value is not None:
        ann.value = body.value
    if body.source is not None:
        ann.source = body.source
    db.commit()
    db.refresh(ann)
    return ann
