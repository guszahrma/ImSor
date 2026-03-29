from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import Annotation, User
from ..schemas import AnnotationCreate, AnnotationOut

router = APIRouter(prefix="/annotations", tags=["annotations"])


@router.post("/", response_model=AnnotationOut)

def create_annotation(
    annotation: AnnotationCreate,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("admin", "user")),
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
