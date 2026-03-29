from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import Image, User
from ..schemas import ImageCreate, ImageOut

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/", response_model=ImageOut)
def register_image(
    image: ImageCreate,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("admin", "user")),
):
    db_image = Image(**image.model_dump())
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image


@router.put("/{image_id}", response_model=ImageOut)
def update_image(
    image_id: int,
    image: ImageCreate,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("admin", "user")),
):
    db_image = db.query(Image).filter(Image.id == image_id).first()
    if not db_image:
        raise HTTPException(status_code=404, detail="Image not found")
    for key, value in image.model_dump().items():
        setattr(db_image, key, value)
    db.commit()
    db.refresh(db_image)
    return db_image


@router.get("/", response_model=list[ImageOut])
def list_images(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    scanner_host: str | None = Query(None),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    query = db.query(Image)
    if scanner_host is not None:
        query = query.filter(Image.scanner_host == scanner_host)
    return query.offset(skip).limit(limit).all()


@router.get("/{image_id}", response_model=ImageOut)
def get_image(
    image_id: int,
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return image
