import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, ForeignKey, Text,
    UniqueConstraint, Boolean,
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="unwelcomed")  # "superuser", "maintainer", "basic-user", "unwelcomed"
    can_create_community = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    annotations = relationship("Annotation", back_populates="user")
    sharing_decisions = relationship("SharingPermission", back_populates="user")
    cameras = relationship("Camera", back_populates="user", cascade="all, delete-orphan")
    persons = relationship("Person", back_populates="user")
    created_communities = relationship("Community", back_populates="creator", cascade="all, delete-orphan")


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
    exif_orientation = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    annotations = relationship("Annotation", back_populates="image")
    sharing_permissions = relationship("SharingPermission", back_populates="image")


class DuplicatePair(Base):
    __tablename__ = "duplicate_pairs"

    id = Column(Integer, primary_key=True, index=True)
    image_a_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    image_b_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    match_type = Column(String(50), default="checksum")  # e.g. "checksum", "visual"
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


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    make = Column(String(200), nullable=False)
    model = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="cameras")

    __table_args__ = (
        UniqueConstraint("user_id", "make", "model", name="uq_camera_user_make_model"),
    )


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    birthdate = Column(Date, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="persons")

    __table_args__ = (
        UniqueConstraint("name", name="uq_persons_name"),
    )


class Community(Base):
    __tablename__ = "communities"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    creator = relationship("User", back_populates="created_communities")
    members = relationship("CommunityMember", back_populates="community", cascade="all, delete-orphan")
    granters = relationship("CommunityGranter", back_populates="community", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("creator_id", "name", name="uq_community_creator_name"),
    )


class CommunityMember(Base):
    __tablename__ = "community_members"

    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    community = relationship("Community", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("community_id", "user_id", name="uq_community_member"),
    )


class CommunityGranter(Base):
    __tablename__ = "community_granters"

    id = Column(Integer, primary_key=True, index=True)
    community_id = Column(Integer, ForeignKey("communities.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    community = relationship("Community", back_populates="granters")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("community_id", "user_id", name="uq_community_granter"),
    )


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
