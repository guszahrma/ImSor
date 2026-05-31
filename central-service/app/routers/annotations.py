import json as json_mod
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import Annotation, Camera, Image, User
from ..schemas import AnnotationCreate, AnnotationOut, AnnotationUpdate, ClusterVoteSubmit, ImageOut, RotationSet

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


@router.get("/rating-queue")
def rating_queue(
    user_id: int,
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    """Return images for the rating queue.
    Superusers see all images with date_taken >= 2007-11-01.
    Other users see only Nominated images (images any user has rated).
    Skipped and duplicate-copy images are excluded.
    Unrated images come first, both groups randomized."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    DATE_CUTOFF = datetime(2007, 11, 1)

    if user.role == "superuser":
        images = db.query(Image).filter(
            Image.date_taken.isnot(None),
            Image.date_taken >= DATE_CUTOFF,
        ).all()
    else:
        # Non-superusers see only Nominated images (any slideshow_rating exists)
        nominated_ids = {
            a.image_id for a in db.query(Annotation).filter(
                Annotation.annotation_type == "slideshow_rating"
            ).all()
        }
        if not nominated_ids:
            return []
        images = db.query(Image).filter(
            Image.id.in_(nominated_ids),
            Image.date_taken.isnot(None),
            Image.date_taken >= DATE_CUTOFF,
        ).all()

    # Exclude duplicate copies
    copy_image_ids: set[int] = set()
    for dr in db.query(Annotation).filter(Annotation.annotation_type == "duplicate_role").all():
        try:
            if int(dr.value) != dr.image_id:
                copy_image_ids.add(dr.image_id)
        except (ValueError, TypeError):
            pass
    images = [img for img in images if img.id not in copy_image_ids]

    # Exclude images this user has skipped
    skipped_ids = {
        a.image_id for a in db.query(Annotation).filter(
            Annotation.user_id == user_id,
            Annotation.annotation_type == "skip",
        ).all()
    }
    images = [img for img in images if img.id not in skipped_ids]

    # Fetch this user's ratings, veto, and rotation annotations
    rated = {
        r.image_id: r for r in db.query(Annotation).filter(
            Annotation.user_id == user_id,
            Annotation.annotation_type == "slideshow_rating",
        ).all()
    }
    vetoed = {
        v.image_id: v for v in db.query(Annotation).filter(
            Annotation.user_id == user_id,
            Annotation.annotation_type == "veto",
        ).all()
    }
    rotations = {
        a.image_id: a for a in db.query(Annotation).filter(
            Annotation.annotation_type == "rotation_correction",
        ).all()
    }

    result = []
    for image in images:
        ann = rated.get(image.id)
        veto = vetoed.get(image.id)
        rot = rotations.get(image.id)
        result.append({
            "image_id": image.id,
            "rating": int(ann.value) if ann is not None else None,
            "annotation_id": ann.id if ann is not None else None,
            "veto_annotation_id": veto.id if veto is not None else None,
            "exif_orientation": image.exif_orientation or 0,
            "rotation_correction": int(rot.value) if rot is not None else 0,
        })

    # Unrated first, both groups randomized
    unrated = [r for r in result if r["rating"] is None]
    rated_list = [r for r in result if r["rating"] is not None]
    random.shuffle(unrated)
    random.shuffle(rated_list)
    return unrated + rated_list


@router.get("/slideshow-queue")
def slideshow_queue(
    user_id: int,
    min_rating: float = Query(7.0),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    """Return images accessible to the user with community average slideshow_rating,
    filtered by minimum average rating. Shuffled order. Excludes duplicate copies."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Access filter: superuser sees all, others see their camera's images
    if user.role == "superuser":
        images = db.query(Image).all()
    else:
        user_cameras = db.query(Camera).filter(Camera.user_id == user_id).all()
        cam_pairs = {(c.make, c.model) for c in user_cameras}
        if not cam_pairs:
            return []
        conditions = [
            and_(Image.camera_make == make, Image.camera_model == model)
            for make, model in cam_pairs
        ]
        images = db.query(Image).filter(or_(*conditions)).all()

    # Exclude images that have been resolved as copies in any duplicate_role vote
    copy_image_ids: set[int] = set()
    dup_roles = db.query(Annotation).filter(
        Annotation.annotation_type == "duplicate_role"
    ).all()
    for dr in dup_roles:
        try:
            if int(dr.value) != dr.image_id:
                copy_image_ids.add(dr.image_id)
        except (ValueError, TypeError):
            pass

    images = [img for img in images if img.id not in copy_image_ids]

    # Exclude vetoed images (any user's veto excludes the image from slideshow)
    vetoed_ids = {
        a.image_id for a in db.query(Annotation).filter(
            Annotation.annotation_type == "veto"
        ).all()
    }
    images = [img for img in images if img.id not in vetoed_ids]

    # Fetch all slideshow_rating annotations (not just current user)
    ratings = db.query(Annotation).filter(
        Annotation.annotation_type == "slideshow_rating"
    ).all()

    # Calculate average rating per image
    ratings_by_image: dict[int, list[int]] = {}
    for r in ratings:
        try:
            val = int(r.value)
            ratings_by_image.setdefault(r.image_id, []).append(val)
        except (ValueError, TypeError):
            pass

    result = []
    for image in images:
        if image.id in ratings_by_image:
            vals = ratings_by_image[image.id]
            avg = sum(vals) / len(vals) if vals else None
            if avg is not None and avg >= min_rating:
                result.append({
                    "image_id": image.id,
                    "avg_rating": round(avg, 1),
                    "rating_count": len(vals),
                })

    # Shuffle for variety
    random.shuffle(result)
    return result


@router.put("/rotation/{image_id}")
def set_rotation(
    image_id: int,
    body: RotationSet,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    existing = db.query(Annotation).filter_by(
        image_id=image_id,
        annotation_type="rotation_correction",
    ).first()
    if body.degrees == 0:
        if existing:
            db.delete(existing)
            db.commit()
        return None
    if existing:
        existing.value = str(body.degrees)
        db.commit()
        db.refresh(existing)
        return existing
    ann = Annotation(
        image_id=image_id,
        annotation_type="rotation_correction",
        value=str(body.degrees),
        source="manual",
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return ann


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
