import datetime
from pydantic import BaseModel


# --- Users ---

class UserCreate(BaseModel):
    username: str
    display_name: str | None = None
    password: str
    role: str = "user"  # "superuser", "maintainer", "user"

class UserOut(BaseModel):
    id: int
    username: str
    display_name: str | None
    role: str
    created_at: datetime.datetime
    model_config = {"from_attributes": True}


# --- Auth ---

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Setup Wizard ---

class SetupRequest(BaseModel):
    username: str
    display_name: str | None = None
    password: str


# --- Images ---

class ImageCreate(BaseModel):
    file_path: str
    file_name: str
    file_size: int | None = None
    checksum: str | None = None
    scanner_host: str | None = None
    date_taken: datetime.datetime | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    image_width: int | None = None
    image_height: int | None = None

class ImageOut(BaseModel):
    id: int
    file_path: str
    file_name: str
    file_size: int | None
    checksum: str | None
    scanner_host: str | None
    date_taken: datetime.datetime | None
    gps_latitude: float | None
    gps_longitude: float | None
    camera_make: str | None
    camera_model: str | None
    image_width: int | None
    image_height: int | None
    created_at: datetime.datetime
    model_config = {"from_attributes": True}


# --- Duplicate Pairs ---

class DuplicatePairCreate(BaseModel):
    image_a_id: int
    image_b_id: int
    match_type: str = "checksum"

class DuplicatePairResolve(BaseModel):
    resolution: str  # "keep_a", "keep_b", "keep_both"

class DuplicatePairOut(BaseModel):
    id: int
    image_a_id: int
    image_b_id: int
    match_type: str
    resolved: bool
    resolution: str | None
    created_at: datetime.datetime
    model_config = {"from_attributes": True}


# --- Annotations ---

class AnnotationCreate(BaseModel):
    image_id: int
    user_id: int | None = None
    annotation_type: str
    value: str
    source: str = "manual"

class AnnotationOut(BaseModel):
    id: int
    image_id: int
    user_id: int | None
    annotation_type: str
    value: str
    source: str
    created_at: datetime.datetime
    model_config = {"from_attributes": True}


class AnnotationUpdate(BaseModel):
    value: str | None = None
    source: str | None = None


# --- Sharing Permissions ---

class SharingPermissionCreate(BaseModel):
    image_id: int
    user_id: int
    decision: str  # "allow" or "veto"

class SharingPermissionOut(BaseModel):
    id: int
    image_id: int
    user_id: int
    decision: str
    created_at: datetime.datetime
    model_config = {"from_attributes": True}
