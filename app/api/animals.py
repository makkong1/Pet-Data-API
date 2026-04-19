from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.animal import AbandonedAnimal
from app.schemas.animal import AnimalListResponse, AnimalResponse

router = APIRouter(prefix="/animals", tags=["animals"])


@router.get("", response_model=AnimalListResponse)
async def list_animals(
    cursor: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    region: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    animal_type: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    if search:
        result = await db.execute(
            text("""
                SELECT * FROM abandoned_animals
                WHERE (:cursor = 0 OR id > :cursor)
                  AND breed % :search
                ORDER BY similarity(breed, :search) DESC, id ASC
                LIMIT :limit
            """),
            {"cursor": cursor, "search": search, "limit": limit + 1},
        )
        rows = result.mappings().all()
        items = [AbandonedAnimal(**dict(r)) for r in rows]
    else:
        stmt = select(AbandonedAnimal)
        if cursor:
            stmt = stmt.where(AbandonedAnimal.id > cursor)
        if region:
            stmt = stmt.where(AbandonedAnimal.region == region)
        if status_filter:
            stmt = stmt.where(AbandonedAnimal.status == status_filter)
        if animal_type:
            stmt = stmt.where(AbandonedAnimal.animal_type == animal_type)
        stmt = stmt.order_by(AbandonedAnimal.id).limit(limit + 1)
        result = await db.execute(stmt)
        items = list(result.scalars().all())

    has_next = len(items) > limit
    items = items[:limit]
    next_cursor = items[-1].id if has_next and items else None
    return AnimalListResponse(items=items, next_cursor=next_cursor, has_next=has_next)


@router.get("/{animal_id}", response_model=AnimalResponse)
async def get_animal(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    result = await db.execute(
        select(AbandonedAnimal).where(AbandonedAnimal.id == animal_id)
    )
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Animal not found")
    return animal
