import json

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from ..auth import require_role
from ..database import get_db
from ..models import User, Camera, PersonUserLink, Annotation, Image
from ..schemas import CameraCreate, CameraOut, PersonUserLinkCreate, PersonUserLinkOut, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Camera make/model values present in the image library ---

@router.get("/image-cameras")
def list_image_cameras(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    """Return distinct (make, model) pairs found in the images table."""
    rows = (
        db.query(Image.camera_make, Image.camera_model)
        .filter(Image.camera_make.isnot(None), Image.camera_model.isnot(None))
        .distinct()
        .all()
    )
    return [{"make": r.camera_make, "model": r.camera_model} for r in rows]


# --- Camera assignments ---

@router.get("/cameras", response_model=list[CameraOut])
def list_cameras(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    return db.query(Camera).all()


@router.post("/cameras", response_model=CameraOut)
def create_camera(
    data: CameraCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    cam = Camera(user_id=data.user_id, make=data.make, model=data.model)
    db.add(cam)
    try:
        db.commit()
        db.refresh(cam)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Camera assignment already exists")
    return cam


@router.delete("/cameras/{camera_id}")
def delete_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    db.delete(cam)
    db.commit()
    return {"detail": "Deleted"}


# --- Person-name → User links ---

@router.get("/person-names")
def list_person_names(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    """Return distinct person names from person_bbox annotations."""
    anns = db.query(Annotation).filter(Annotation.annotation_type == "person_bbox").all()
    names: set[str] = set()
    for ann in anns:
        try:
            val = json.loads(ann.value)
            name = val.get("person_name")
            if name:
                names.add(name)
        except (json.JSONDecodeError, TypeError):
            pass
    return sorted(names)


@router.get("/person-links", response_model=list[PersonUserLinkOut])
def list_person_links(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    return db.query(PersonUserLink).all()


@router.post("/person-links", response_model=PersonUserLinkOut)
def create_person_link(
    data: PersonUserLinkCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    link = PersonUserLink(person_name=data.person_name, user_id=data.user_id)
    db.add(link)
    try:
        db.commit()
        db.refresh(link)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Link already exists")
    return link


@router.delete("/person-links/{link_id}")
def delete_person_link(
    link_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    link = db.query(PersonUserLink).filter(PersonUserLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
    return {"detail": "Deleted"}


# --- Community creation access ---

@router.patch("/users/{user_id}/can-create-community", response_model=UserOut)
def set_can_create_community(
    user_id: int,
    value: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.can_create_community = value
    db.commit()
    db.refresh(user)
    return user
