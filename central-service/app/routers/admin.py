import json

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from ..auth import require_role
from ..database import get_db
from ..models import User, Camera, Person, Annotation, Image, CameraModelSettings
from ..schemas import (
    CameraCreate, CameraOut, CameraModelSettingsOut, CameraModelSettingsPatch,
    PersonBirthdateUpdate, PersonCreate, PersonOut, UserOut,
)

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


# --- Camera model settings (per-make/model EXIF overrides) ---

@router.get("/camera-model-settings", response_model=list[CameraModelSettingsOut])
def list_camera_model_settings(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    """Return all distinct (make, model) from images, merged with any stored settings."""
    image_cameras = (
        db.query(Image.camera_make, Image.camera_model)
        .filter(Image.camera_make.isnot(None), Image.camera_model.isnot(None))
        .distinct()
        .all()
    )
    settings_map = {
        (s.make, s.model): s.skip_exif_rotation
        for s in db.query(CameraModelSettings).all()
    }
    return [
        CameraModelSettingsOut(
            make=r.camera_make,
            model=r.camera_model,
            skip_exif_rotation=settings_map.get((r.camera_make, r.camera_model), False),
        )
        for r in image_cameras
    ]


@router.patch("/camera-model-settings", response_model=CameraModelSettingsOut)
def upsert_camera_model_setting(
    data: CameraModelSettingsPatch,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    """Upsert skip_exif_rotation for a (make, model) pair."""
    setting = (
        db.query(CameraModelSettings)
        .filter(CameraModelSettings.make == data.make, CameraModelSettings.model == data.model)
        .first()
    )
    if setting:
        setting.skip_exif_rotation = data.skip_exif_rotation
    else:
        setting = CameraModelSettings(
            make=data.make, model=data.model, skip_exif_rotation=data.skip_exif_rotation
        )
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return CameraModelSettingsOut(
        make=setting.make, model=setting.model, skip_exif_rotation=setting.skip_exif_rotation
    )


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
    # Backfill unattributed images if this is now the only Camera record for (make, model)
    camera_count = (
        db.query(Camera)
        .filter(Camera.make == data.make, Camera.model == data.model)
        .count()
    )
    if camera_count == 1:
        db.query(Image).filter(
            Image.camera_make == data.make,
            Image.camera_model == data.model,
            Image.image_responsible_id.is_(None),
        ).update({"image_responsible_id": data.user_id})
        db.commit()
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


@router.get("/persons", response_model=list[PersonOut])
def list_persons(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    return db.query(Person).order_by(Person.name).all()


@router.get("/person-links", response_model=list[PersonOut])
def list_person_links(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    return db.query(Person).filter(Person.user_id.isnot(None)).all()


@router.post("/person-links", response_model=PersonOut)
def create_person_link(
    data: PersonCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    existing = db.query(Person).filter(Person.name == data.name).first()
    if existing:
        existing.user_id = data.user_id
        db.commit()
        db.refresh(existing)
        return existing
    person = Person(name=data.name, user_id=data.user_id)
    db.add(person)
    try:
        db.commit()
        db.refresh(person)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Person already exists")
    return person


@router.patch("/persons/{person_id}", response_model=PersonOut)
def update_person_birthdate(
    person_id: int,
    data: PersonBirthdateUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    person.birthdate = data.birthdate
    db.commit()
    db.refresh(person)
    return person


@router.delete("/person-links/{link_id}")
def delete_person_link(
    link_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("superuser")),
):
    person = db.query(Person).filter(Person.id == link_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    person.user_id = None
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
