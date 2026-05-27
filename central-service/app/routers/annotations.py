import json as json_mod

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import Annotation, Image, User
from ..schemas import AnnotationCreate, AnnotationOut, AnnotationUpdate, ClusterVoteSubmit, ImageOut

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


@router.get("/bbox-queue")
def bbox_queue(
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    """Return images that have at least one unnamed person_bbox, ordered:
    fully unworked (0 named) first, then partially named; sorted by unnamed_count desc within each group."""
    anns = db.query(Annotation).filter(
        Annotation.annotation_type == "person_bbox"
    ).all()

    by_image: dict[int, dict] = {}
    for ann in anns:
        counts = by_image.setdefault(ann.image_id, {"named": 0, "unnamed": 0})
        try:
            val = json_mod.loads(ann.value)
            if val.get("person_name"):
                counts["named"] += 1
            else:
                counts["unnamed"] += 1
        except (json_mod.JSONDecodeError, TypeError):
            counts["unnamed"] += 1

    queue = [
        {"image_id": img_id, "named_count": c["named"], "unnamed_count": c["unnamed"]}
        for img_id, c in by_image.items()
        if c["unnamed"] > 0
    ]
    queue.sort(key=lambda x: (x["named_count"] > 0, -x["unnamed_count"]))
    return queue


@router.get("/bbox-image/{image_id}")
def bbox_image(
    image_id: int,
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    """Return image metadata and its person_bbox annotations."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    anns = db.query(Annotation).filter(
        Annotation.image_id == image_id,
        Annotation.annotation_type == "person_bbox",
    ).all()
    return {
        "image": ImageOut.model_validate(image),
        "annotations": [AnnotationOut.model_validate(a) for a in anns],
    }


@router.delete("/{annotation_id}")
def delete_annotation(
    annotation_id: int,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    ann = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")
    db.delete(ann)
    db.commit()
    return {"detail": "Deleted"}


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
