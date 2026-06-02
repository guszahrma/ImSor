import json as json_mod
import random
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, cast, Float, func, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import Annotation, Camera, Image, Person, PersonBboxDismissal, PersonIdentity, User
from ..schemas import (AnnotationCreate, AnnotationOut, AnnotationUpdate, ClusterVoteSubmit,
                       ImageOut, PersonBboxDismissalCreate, PersonIdentityCreate, PersonIdentityOut,
                       RotationSet)

router = APIRouter(prefix="/annotations", tags=["annotations"])


def _clamp_bbox_value(value_str: str, image: Image) -> str:
    """Clamp person_bbox coordinates to image bounds. No-op if dimensions unknown."""
    if not image.image_width or not image.image_height:
        return value_str
    try:
        val = json_mod.loads(value_str)
        x = max(0, val["x"])
        y = max(0, val["y"])
        x = min(x, image.image_width - 1)
        y = min(y, image.image_height - 1)
        w = min(val["width"],  image.image_width  - x)
        h = min(val["height"], image.image_height - y)
        if w <= 0 or h <= 0:
            return value_str
        val["x"] = x
        val["y"] = y
        val["width"]  = w
        val["height"] = h
        return json_mod.dumps(val)
    except (json_mod.JSONDecodeError, TypeError, KeyError):
        return value_str


@router.post("/", response_model=AnnotationOut)
def create_annotation(
    annotation: AnnotationCreate,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    data = annotation.model_dump()
    if data["annotation_type"] == "person_bbox":
        image = db.query(Image).filter(Image.id == data["image_id"]).first()
        if image:
            data["value"] = _clamp_bbox_value(data["value"], image)
    db_annotation = Annotation(**data)
    db.add(db_annotation)
    db.commit()
    db.refresh(db_annotation)
    return db_annotation


@router.get("/", response_model=list[AnnotationOut])
def list_annotations(
    image_id: int | None = Query(None),
    annotation_type: str | None = Query(None),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    query = db.query(Annotation)
    if image_id is not None:
        query = query.filter(Annotation.image_id == image_id)
    if annotation_type is not None:
        query = query.filter(Annotation.annotation_type == annotation_type)
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


@router.get("/known-people")
def known_people(
    user_id: int = Query(...),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    """Return person names ordered by most recently used by this user, then alphabetically."""
    persons = db.query(Person).all()
    latest: dict[int, datetime] = {}
    for pi in db.query(PersonIdentity).filter(
        PersonIdentity.person_id.isnot(None),
        PersonIdentity.user_id == user_id,
    ).all():
        if pi.person_id not in latest or pi.created_at > latest[pi.person_id]:
            latest[pi.person_id] = pi.created_at

    def sort_key(p: Person):
        ts = latest.get(p.id)
        return (0 if ts else 1, -(ts.timestamp() if ts else 0), p.name)

    return [p.name for p in sorted(persons, key=sort_key)]


@router.get("/bbox-queue")
def bbox_queue(
    user_id: int = Query(...),
    active_model: str | None = Query(None),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    """Return images with person_bbox detections, ordered by the 5-tier annotation priority."""
    DATE_CUTOFF = datetime(2007, 11, 8)

    # Load AI detections
    ann_query = db.query(Annotation).filter(Annotation.annotation_type == "person_bbox")
    if active_model:
        ann_query = ann_query.filter(Annotation.source == f"ai:{active_model}")
    else:
        ann_query = ann_query.filter(Annotation.source.like("ai:%"))
    ai_anns = ann_query.all()
    if not ai_anns:
        return []

    # Filter by date_taken cutoff
    all_image_ids = {ann.image_id for ann in ai_anns}
    eligible_ids = {
        img.id for img in db.query(Image).filter(
            Image.id.in_(all_image_ids),
            Image.date_taken >= DATE_CUTOFF,
        ).all()
    }
    ai_anns = [ann for ann in ai_anns if ann.image_id in eligible_ids]
    if not ai_anns:
        return []

    # Exclude duplicate copies
    copy_image_ids: set[int] = set()
    for dr in db.query(Annotation).filter(Annotation.annotation_type == "duplicate_role").all():
        try:
            if int(dr.value) != dr.image_id:
                copy_image_ids.add(dr.image_id)
        except (ValueError, TypeError):
            pass
    ai_anns = [ann for ann in ai_anns if ann.image_id not in copy_image_ids]
    if not ai_anns:
        return []

    ai_det_ids = {ann.id for ann in ai_anns}
    ai_by_image: dict[int, list[int]] = {}
    for ann in ai_anns:
        ai_by_image.setdefault(ann.image_id, []).append(ann.id)

    # Load Detection Adoptions, group by the AI detection they inherit from
    adoptions_by_ai: dict[int, list[Annotation]] = defaultdict(list)
    for ann in db.query(Annotation).filter(
        Annotation.annotation_type == "person_bbox",
        Annotation.source == "manual",
        Annotation.user_id.isnot(None),
    ).all():
        try:
            parent_id = int(json_mod.loads(ann.value).get("inherited_from", 0))
            if parent_id in ai_det_ids:
                adoptions_by_ai[parent_id].append(ann)
        except (json_mod.JSONDecodeError, TypeError, ValueError):
            pass

    # Load person_identities; keep latest per (adoption_id, user_id)
    pi_latest: dict[int, dict[int, PersonIdentity]] = defaultdict(dict)
    for pi in db.query(PersonIdentity).all():
        if pi.user_id is None:
            continue
        existing = pi_latest[pi.bbox_annotation_id].get(pi.user_id)
        if existing is None or pi.created_at > existing.created_at:
            pi_latest[pi.bbox_annotation_id][pi.user_id] = pi

    def identified_by(ai_id: int, uid: int) -> bool:
        for adoption in adoptions_by_ai[ai_id]:
            if adoption.user_id == uid:
                pi = pi_latest[adoption.id].get(uid)
                if pi and pi.person_id is not None:
                    return True
        # Also check PersonIdentity rows pointing directly to the AI detection
        pi = pi_latest[ai_id].get(uid)
        if pi and pi.person_id is not None:
            return True
        return False

    def identified_by_anyone(ai_id: int) -> bool:
        for adoption in adoptions_by_ai[ai_id]:
            for uid, pi in pi_latest[adoption.id].items():
                if pi.person_id is not None:
                    return True
        # Also check PersonIdentity rows pointing directly to the AI detection
        for uid, pi in pi_latest[ai_id].items():
            if pi.person_id is not None:
                return True
        return False

    # Average slideshow_rating per image (for secondary sort within each tier)
    avg_rows = (
        db.query(Annotation.image_id, func.avg(cast(Annotation.value, Float)).label("avg"))
        .filter(
            Annotation.annotation_type == "slideshow_rating",
            Annotation.image_id.in_(ai_by_image.keys()),
        )
        .group_by(Annotation.image_id)
        .all()
    )
    avg_rating: dict[int, float] = {row.image_id: row.avg for row in avg_rows}

    result = []
    for image_id, det_ids in ai_by_image.items():
        total = len(det_ids)
        any_count  = sum(1 for d in det_ids if identified_by_anyone(d))
        user_count = sum(1 for d in det_ids if identified_by(d, user_id))

        if any_count == 0:
            tier = 1
        elif any_count < total and user_count == 0:
            tier = 2
        elif any_count == total and user_count == 0:
            tier = 3
        elif user_count < total:
            tier = 4
        else:
            tier = 5

        result.append({
            "image_id": image_id,
            "tier": tier,
            "total_count": total,
            "any_identified_count": any_count,
            "user_identified_count": user_count,
            # Legacy compat fields
            "named_count": any_count,
            "unnamed_count": total - any_count,
        })

    result.sort(key=lambda x: (x["tier"], -(avg_rating.get(x["image_id"]) or 0), -x["total_count"]))
    return result


@router.get("/bbox-image/{image_id}")
def bbox_image(
    image_id: int,
    user_id: int = Query(...),
    active_model: str | None = Query(None),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    """Return image metadata and its person_bbox annotations, user-aware.

    For each AI detection, returns the user's Detection Adoption if one exists
    (with their adjusted geometry), otherwise the AI detection. Person name is
    hydrated from the user's latest PersonIdentity.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # AI detections for this image
    ai_query = db.query(Annotation).filter(
        Annotation.image_id == image_id,
        Annotation.annotation_type == "person_bbox",
    )
    if active_model:
        ai_query = ai_query.filter(Annotation.source == f"ai:{active_model}")
    else:
        ai_query = ai_query.filter(Annotation.source.like("ai:%"))
    ai_anns = ai_query.all()
    ai_ids = {ann.id for ann in ai_anns}

    # Current user's manual person_bbox annotations for this image
    user_manual_anns = db.query(Annotation).filter(
        Annotation.image_id == image_id,
        Annotation.annotation_type == "person_bbox",
        Annotation.source == "manual",
        Annotation.user_id == user_id,
    ).all()

    # Split into Detection Adoptions (have inherited_from) and standalone drawn bboxes
    adoptions_by_ai: dict[int, Annotation] = {}
    standalone: list[Annotation] = []
    for ann in user_manual_anns:
        try:
            parent_id = int(json_mod.loads(ann.value).get("inherited_from", 0))
            if parent_id in ai_ids:
                adoptions_by_ai[parent_id] = ann
                continue
        except (json_mod.JSONDecodeError, TypeError, ValueError):
            pass
        standalone.append(ann)

    # Latest PersonIdentity per adoption (for this user)
    adoption_ids = [a.id for a in adoptions_by_ai.values()]
    pi_by_adoption: dict[int, PersonIdentity] = {}
    if adoption_ids:
        for pi in db.query(PersonIdentity).filter(
            PersonIdentity.bbox_annotation_id.in_(adoption_ids),
            PersonIdentity.user_id == user_id,
        ).order_by(PersonIdentity.created_at.desc()).all():
            pi_by_adoption.setdefault(pi.bbox_annotation_id, pi)

    # Person names for identified detections
    person_ids = {pi.person_id for pi in pi_by_adoption.values() if pi.person_id}
    person_names: dict[int, str] = {}
    if person_ids:
        person_names = {p.id: p.name for p in db.query(Person).filter(Person.id.in_(person_ids)).all()}

    # Build response: one entry per AI detection (adoption or raw AI), plus standalone drawn bboxes
    result_anns = []
    for ai_ann in ai_anns:
        adoption = adoptions_by_ai.get(ai_ann.id)
        base = adoption if adoption else ai_ann
        val = json_mod.loads(base.value)
        pi = pi_by_adoption.get(adoption.id) if adoption else None
        if pi:
            val["person_name"] = person_names.get(pi.person_id) if pi.person_id else None
            val["person_id"] = pi.person_id
        else:
            val["person_id"] = None
            # person_name kept from annotation value as fallback (legacy PATCH flow)
        val["ai_annotation_id"] = ai_ann.id
        out = AnnotationOut.model_validate(base).model_dump()
        out["value"] = json_mod.dumps(val)
        result_anns.append(out)

    for ann in standalone:
        val = json_mod.loads(ann.value)
        val.setdefault("person_id", None)
        val.setdefault("ai_annotation_id", None)
        out = AnnotationOut.model_validate(ann).model_dump()
        out["value"] = json_mod.dumps(val)
        result_anns.append(out)

    return {"image": ImageOut.model_validate(image), "annotations": result_anns}


@router.post("/person-identities", response_model=PersonIdentityOut)
def create_person_identity(
    body: PersonIdentityCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    """Append a Person Identification for the current user."""
    pi = PersonIdentity(
        bbox_annotation_id=body.bbox_annotation_id,
        person_id=body.person_id,
        user_id=current.id,
    )
    db.add(pi)
    db.commit()
    db.refresh(pi)
    return pi


@router.post("/person-bbox-dismissals")
def dismiss_person_bbox(
    body: PersonBboxDismissalCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    """Record that the current user considers this AI detection irrelevant."""
    existing = db.query(PersonBboxDismissal).filter_by(
        user_id=current.id,
        bbox_annotation_id=body.bbox_annotation_id,
    ).first()
    if existing:
        return {"detail": "already dismissed"}
    db.add(PersonBboxDismissal(user_id=current.id, bbox_annotation_id=body.bbox_annotation_id))
    db.commit()

    # Hard-delete the AI detection if 5+ users have dismissed it and nobody adopted it
    dismissal_count = db.query(PersonBboxDismissal).filter_by(
        bbox_annotation_id=body.bbox_annotation_id
    ).count()
    if dismissal_count >= 5:
        has_adoption = db.query(Annotation).filter(
            Annotation.annotation_type == "person_bbox",
            Annotation.source == "manual",
        ).all()
        adopted = any(
            int(json_mod.loads(a.value).get("inherited_from", 0)) == body.bbox_annotation_id
            for a in has_adoption
            if _safe_inherited_from(a.value) == body.bbox_annotation_id
        )
        if not adopted:
            ann = db.query(Annotation).filter(Annotation.id == body.bbox_annotation_id).first()
            if ann:
                db.delete(ann)
                db.commit()
    return {"detail": "dismissed"}


def _safe_inherited_from(value: str) -> int | None:
    try:
        return int(json_mod.loads(value).get("inherited_from", 0)) or None
    except (json_mod.JSONDecodeError, TypeError, ValueError):
        return None


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
    bookmarks = {
        a.image_id: a for a in db.query(Annotation).filter(
            Annotation.user_id == user_id,
            Annotation.annotation_type == "bookmark",
        ).all()
    }

    result = []
    for image in images:
        ann = rated.get(image.id)
        veto = vetoed.get(image.id)
        rot = rotations.get(image.id)
        bm = bookmarks.get(image.id)
        result.append({
            "image_id": image.id,
            "rating": int(ann.value) if ann is not None else None,
            "annotation_id": ann.id if ann is not None else None,
            "veto_annotation_id": veto.id if veto is not None else None,
            "exif_orientation": image.exif_orientation or 0,
            "rotation_correction": int(rot.value) if rot is not None else 0,
            "bookmark_annotation_id": bm.id if bm is not None else None,
            "date_taken": image.date_taken.isoformat() if image.date_taken else None,
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
                    "date_taken": image.date_taken.isoformat() if image.date_taken else None,
                    "latitude":   image.gps_latitude,
                    "longitude":  image.gps_longitude,
                })

    # Shuffle for variety
    random.shuffle(result)

    # Attach Selma's largest bbox per image
    selma = db.query(Person).filter(Person.name == "Selma Zahr").first()
    if selma and result:
        image_ids = {item["image_id"] for item in result}

        # Gather all person_bbox annotations (adoptions + AI) for these images
        all_bboxes = db.query(Annotation).filter(
            Annotation.image_id.in_(image_ids),
            Annotation.annotation_type == "person_bbox",
        ).all()
        bbox_ids = [a.id for a in all_bboxes]

        # Find PersonIdentity rows linking to Selma
        selma_ann_ids: set[int] = set()
        if bbox_ids:
            for pi in db.query(PersonIdentity).filter(
                PersonIdentity.bbox_annotation_id.in_(bbox_ids),
                PersonIdentity.person_id == selma.id,
            ).all():
                selma_ann_ids.add(pi.bbox_annotation_id)

        # Pick the largest Selma bbox per image
        selma_bbox_by_image: dict[int, dict] = {}
        for ann in all_bboxes:
            if ann.id not in selma_ann_ids:
                continue
            try:
                val = json_mod.loads(ann.value)
                area = val.get("width", 0) * val.get("height", 0)
                existing = selma_bbox_by_image.get(ann.image_id)
                if existing is None or area > existing["_area"]:
                    selma_bbox_by_image[ann.image_id] = {
                        "x": val["x"], "y": val["y"],
                        "width": val["width"], "height": val["height"],
                        "_area": area,
                    }
            except (json_mod.JSONDecodeError, KeyError, TypeError):
                pass

        for item in result:
            bbox = selma_bbox_by_image.get(item["image_id"])
            item["selma_bbox"] = (
                {k: bbox[k] for k in ("x", "y", "width", "height")} if bbox else None
            )
    else:
        for item in result:
            item["selma_bbox"] = None

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
        if ann.annotation_type == "person_bbox":
            image = db.query(Image).filter(Image.id == ann.image_id).first()
            ann.value = _clamp_bbox_value(body.value, image) if image else body.value
        else:
            ann.value = body.value
    if body.source is not None:
        ann.source = body.source

    # When person_name is set on a person_bbox, also record a PersonIdentity
    if body.value is not None and ann.annotation_type == "person_bbox":
        try:
            person_name = json_mod.loads(body.value).get("person_name")
            if person_name:
                acting_user_id = body.user_id or _current.id
                person = db.query(Person).filter(Person.name == person_name).first()
                if not person:
                    person = Person(name=person_name)
                    db.add(person)
                    db.flush()
                db.add(PersonIdentity(
                    bbox_annotation_id=ann.id,
                    person_id=person.id,
                    user_id=acting_user_id,
                ))
        except (json_mod.JSONDecodeError, TypeError):
            pass

    db.commit()
    db.refresh(ann)
    return ann
