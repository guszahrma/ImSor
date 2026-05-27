import random

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import Annotation, DuplicatePair, Image, User
from ..schemas import (
    ClusterOut, ClusterImageOut, ClusterVoteSubmit, DuplicateRoleVote,
    DuplicatePairCreate, DuplicatePairOut,
)

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _union_find(pairs: list[DuplicatePair]) -> dict[int, list[int]]:
    """Group image IDs into clusters using union-find. Returns {root: [image_ids]}."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    for pair in pairs:
        union(pair.image_a_id, pair.image_b_id)

    groups: dict[int, list[int]] = {}
    all_ids = {p.image_a_id for p in pairs} | {p.image_b_id for p in pairs}
    for img_id in all_ids:
        root = find(img_id)
        groups.setdefault(root, []).append(img_id)

    return groups


# ---------------------------------------------------------------------------
# Pair management (used by scanner-agent)
# ---------------------------------------------------------------------------

@router.post("/", response_model=DuplicatePairOut)
def create_duplicate_pair(
    pair: DuplicatePairCreate,
    db: Session = Depends(get_db),
    _current: User = Depends(require_role("superuser", "maintainer", "basic-user")),
):
    existing = db.query(DuplicatePair).filter_by(
        image_a_id=pair.image_a_id, image_b_id=pair.image_b_id
    ).first()
    if existing:
        return existing

    db_pair = DuplicatePair(
        image_a_id=pair.image_a_id,
        image_b_id=pair.image_b_id,
        match_type=pair.match_type,
    )
    db.add(db_pair)
    db.commit()
    db.refresh(db_pair)
    return db_pair


# ---------------------------------------------------------------------------
# Cluster queue (used by the web UI)
# ---------------------------------------------------------------------------

@router.get("/clusters", response_model=list[ClusterOut])
def list_clusters(
    user_id: int = Query(..., description="ID of the requesting annotator"),
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    """
    Return Duplicate Clusters ordered by the Annotation Queue rules:
    1. Clusters with zero duplicate_role annotations — semi-random
    2. Clusters the requesting user hasn't voted on — fewest annotators first, semi-random within ties
    Clusters the user has already voted on are excluded.
    """
    pairs = db.query(DuplicatePair).all()
    if not pairs:
        return []

    groups = _union_find(pairs)  # root -> [image_ids]

    # Fetch all duplicate_role annotations in one query
    all_votes = db.query(Annotation).filter(
        Annotation.annotation_type == "duplicate_role"
    ).all()

    # Build lookup: image_id -> list of (user_id, value)
    votes_by_image: dict[int, list[tuple[int, str]]] = {}
    for v in all_votes:
        if v.user_id is not None:
            votes_by_image.setdefault(v.image_id, []).append((v.user_id, v.value))

    # Fetch images
    all_image_ids = list({img_id for ids in groups.values() for img_id in ids})
    images_by_id: dict[int, Image] = {
        img.id: img
        for img in db.query(Image).filter(Image.id.in_(all_image_ids)).all()
    }

    result = []
    for root, image_ids in groups.items():
        # Aggregate annotation info for this cluster
        cluster_user_ids: set[int] = set()
        user_votes_for_cluster: list[DuplicateRoleVote] = []

        for img_id in image_ids:
            for uid, val in votes_by_image.get(img_id, []):
                cluster_user_ids.add(uid)
                if uid == user_id:
                    user_votes_for_cluster.append(
                        DuplicateRoleVote(image_id=img_id, value=val)
                    )

        already_voted = user_id in cluster_user_ids

        if already_voted:
            continue  # exclude from queue

        annotator_count = len(cluster_user_ids)

        cluster_images = [
            ClusterImageOut.model_validate(images_by_id[img_id])
            for img_id in sorted(image_ids)
            if img_id in images_by_id
        ]

        result.append(ClusterOut(
            cluster_id=min(image_ids),
            images=cluster_images,
            annotator_count=annotator_count,
            current_user_voted=False,
            current_user_votes=[],
        ))

    # Sort: zero-annotation clusters first, then by fewest annotators,
    # then shuffle within each tier for semi-random ordering
    random.shuffle(result)
    result.sort(key=lambda c: (c.annotator_count > 0, c.annotator_count))

    return result
