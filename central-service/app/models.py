import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # "superuser", "maintainer", "user"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    annotations = relationship("Annotation", back_populates="user")
    sharing_decisions = relationship("SharingPermission", back_populates="user")


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(Text, nullable=False)
    file_name = Column(String(500), nullable=False)
    file_size = Column(Integer)
    checksum = Column(String(128), index=True)
    scanner_host = Column(String(200))

    # EXIF metadata
    date_taken = Column(DateTime)
    gps_latitude = Column(Float)
    gps_longitude = Column(Float)
    camera_make = Column(String(200))
    camera_model = Column(String(200))
    image_width = Column(Integer)
    image_height = Column(Integer)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    annotations = relationship("Annotation", back_populates="image")
    sharing_permissions = relationship("SharingPermission", back_populates="image")


class DuplicatePair(Base):
    __tablename__ = "duplicate_pairs"

    id = Column(Integer, primary_key=True, index=True)
    image_a_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    image_b_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    match_type = Column(String(50), default="checksum")  # e.g. "checksum", "visual"
    resolved = Column(Boolean, default=False)
    resolution = Column(String(50))  # e.g. "keep_a", "keep_b", "keep_both"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    image_a = relationship("Image", foreign_keys=[image_a_id])
    image_b = relationship("Image", foreign_keys=[image_b_id])

    __table_args__ = (
        UniqueConstraint("image_a_id", "image_b_id", name="uq_duplicate_pair"),
    )


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    annotation_type = Column(String(50), nullable=False)  # e.g. "person", "location", "tag", "description"
    value = Column(Text, nullable=False)
    source = Column(String(50), default="manual")  # "manual" or "ai"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    image = relationship("Image", back_populates="annotations")
    user = relationship("User", back_populates="annotations")


class SharingPermission(Base):
    __tablename__ = "sharing_permissions"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    decision = Column(String(20), nullable=False)  # "allow" or "veto"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    image = relationship("Image", back_populates="sharing_permissions")
    user = relationship("User", back_populates="sharing_decisions")

    __table_args__ = (
        UniqueConstraint("image_id", "user_id", name="uq_sharing_image_user"),
    )
