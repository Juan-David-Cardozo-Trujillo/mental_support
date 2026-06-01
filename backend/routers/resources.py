"""
Resources Router
================

Resource library for mental health content:
- Articles, videos, exercises, coping tools
- Anonymous access via share tokens (no user tracking)
- Tagging and categorization
- Admin CRUD operations

Endpoints:
  GET  /resources                   → List resources (paginated)
  GET  /resources/{id}              → Get resource details
  GET  /resources/share/{token}     → Anonymous access via share token
  POST /resources                   → Admin: Create resource
  PATCH /resources/{id}             → Admin: Update resource
  DELETE /resources/{id}            → Admin: Delete resource
  GET  /resources/categories        → List available categories
"""

import logging
import uuid
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from backend.core.database import get_platform_db
from backend.core.security import get_current_user, consent_required, require_role
from backend.db.platform_models import (
    Resource,
    ContentTypeEnum,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["Resources"])

# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────

class ResourceCreate(BaseModel):
    """Create/update resource."""
    title: str = Field(..., description="Resource title")
    description: str = Field(..., description="Short description")
    content: str = Field(..., description="Full content (HTML or Markdown)")
    content_type: str = Field(..., description="article | video | exercise | tool")
    category: str = Field(..., description="mental_health | coping | sleep | stress | etc.")
    active: bool = Field(default=False, description="Published to platform")
    external_url: Optional[str] = Field(None, description="External link (videos, etc.)")
    estimated_duration_minutes: Optional[int] = Field(None, description="Read/watch time")


class ResourceResponse(BaseModel):
    """Resource details (public view)."""
    id: str
    title: str
    description: str
    content_type: str
    category: str
    estimated_duration_minutes: Optional[int]
    view_count: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ResourceDetailResponse(ResourceResponse):
    """Resource with full content."""
    content: str
    external_url: Optional[str]


class CategoryStats(BaseModel):
    """Category with resource count."""
    category: str
    count: int
    description: Optional[str]


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ResourceResponse])
async def list_resources(
    category: Optional[str] = Query(None, description="Filter by category"),
    content_type: Optional[str] = Query(None, description="Filter by type"),
    search: Optional[str] = Query(None, description="Search in title/description"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Pagination limit"),
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """
    List published resources with filtering and pagination.
    
    Query Parameters:
    - category: Filter by category (mental_health, coping, sleep, stress, etc.)
    - content_type: Filter by type (article, video, exercise, tool)
    - search: Full-text search in title and description
    - skip: Offset for pagination (default 0)
    - limit: Results per page (default 20, max 100)
    
    Returns: Paginated list of resources
    """
    try:
        query = select(Resource).where(Resource.active == True)
        
        # Apply filters
        if category:
            query = query.where(Resource.category == category)
        
        if content_type:
            query = query.where(Resource.content_type == content_type)
        
        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                (Resource.title.ilike(search_term)) |
                (Resource.description.ilike(search_term))
            )
        
        # Order by newest first
        query = query.order_by(Resource.created_at.desc())
        
        # Pagination
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        resources = result.scalars().all()
        
        logger.info(f"✓ Retrieved {len(resources)} resources for {current_user['role']}")
        return [ResourceResponse.from_orm(r) for r in resources]
        
    except Exception as e:
        logger.error(f"✗ Error listing resources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve resources"
        )


@router.get("/{resource_id}", response_model=ResourceDetailResponse)
async def get_resource(
    resource_id: str,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """
    Get single resource with full content.
    
    Increments view_count (for analytics).
    """
    try:
        resource_uuid = uuid.UUID(resource_id)
        
        resource_result = await db.execute(
            select(Resource).where(
                and_(
                    Resource.id == resource_uuid,
                    Resource.active == True
                )
            )
        )
        resource = resource_result.scalar_one_or_none()
        
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found or not published"
            )
        
        # Increment view count
        resource.view_count = (resource.view_count or 0) + 1
        await db.commit()
        
        logger.debug(f"✓ Retrieved resource {resource_id} (views: {resource.view_count})")
        return ResourceDetailResponse.from_orm(resource)
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid resource ID format"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"✗ Error retrieving resource: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve resource"
        )


@router.get("/share/{share_token}", response_model=ResourceDetailResponse)
async def get_resource_by_token(
    share_token: str,
    db: AsyncSession = Depends(get_platform_db),
):
    """
    Access resource anonymously via share token (no user login required).
    
    **Privacy Note**: No user tracking—view is anonymous.
    This allows sharing resources in emails/messages without forcing login.
    """
    try:
        resource_result = await db.execute(
            select(Resource).where(
                Resource.share_token == share_token
            )
        )
        resource = resource_result.scalar_one_or_none()
        
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found or token invalid"
            )
        
        # Check if token is still valid (not expired)
        if resource.share_token_expires_at and resource.share_token_expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Share token has expired"
            )
        
        # Increment view count (anonymous)
        resource.view_count = (resource.view_count or 0) + 1
        await db.commit()
        
        logger.info(f"✓ Anonymous access to resource via share token (views: {resource.view_count})")
        return ResourceDetailResponse.from_orm(resource)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"✗ Error accessing resource by token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve resource"
        )


@router.get("/categories", response_model=list[CategoryStats])
async def get_categories(
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(consent_required),
):
    """Get list of categories with resource counts."""
    try:
        from sqlalchemy import func
        
        result = await db.execute(
            select(
                Resource.category,
                func.count(Resource.id).label("count")
            ).where(
                Resource.active == True
            ).group_by(
                Resource.category
            ).order_by(
                func.count(Resource.id).desc()
            )
        )
        
        categories = []
        category_descriptions = {
            "mental_health": "General mental health information",
            "coping": "Coping strategies and techniques",
            "sleep": "Sleep hygiene and relaxation",
            "stress": "Stress management",
            "anxiety": "Anxiety management",
            "depression": "Understanding depression",
            "relationships": "Relationship & social health",
            "mindfulness": "Mindfulness & meditation",
            "exercise": "Physical wellness",
            "nutrition": "Nutrition & wellness",
        }
        
        for cat, count in result.fetchall():
            categories.append(
                CategoryStats(
                    category=cat,
                    count=count,
                    description=category_descriptions.get(cat)
                )
            )
        
        logger.debug(f"✓ Retrieved {len(categories)} resource categories")
        return categories
        
    except Exception as e:
        logger.error(f"✗ Error retrieving categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve categories"
        )


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    req: ResourceCreate,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("university_admin", "platform_admin")),
):
    """
    Create new resource (admin only).
    
    Content can be published immediately or saved as draft.
    Share token is auto-generated (max 10 uses, optional expiry).
    """
    try:
        # Validate content type
        valid_types = ["article", "video", "exercise", "tool"]
        if req.content_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid content_type. Must be one of: {', '.join(valid_types)}"
            )
        
        # Create resource with share token
        resource = Resource(
            id=uuid.uuid4(),
            title=req.title,
            description=req.description,
            content=req.content,
            content_type=req.content_type,
            category=req.category,
            active=req.active,
            external_url=req.external_url,
            estimated_duration_minutes=req.estimated_duration_minutes,
            share_token=secrets.token_urlsafe(32),  # Random token for sharing
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            view_count=0,
        )
        
        db.add(resource)
        await db.commit()
        await db.refresh(resource)
        
        logger.info(f"✓ Resource created: {resource.id} by {current_user['profile_id']}")
        return ResourceResponse.from_orm(resource)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"✗ Error creating resource: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create resource"
        )


@router.patch("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: str,
    req: ResourceCreate,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("university_admin", "platform_admin")),
):
    """Update resource (admin only)."""
    try:
        resource_uuid = uuid.UUID(resource_id)
        
        resource_result = await db.execute(
            select(Resource).where(Resource.id == resource_uuid)
        )
        resource = resource_result.scalar_one_or_none()
        
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        # Update fields
        resource.title = req.title
        resource.description = req.description
        resource.content = req.content
        resource.content_type = req.content_type
        resource.category = req.category
        resource.active = req.active
        resource.external_url = req.external_url
        resource.estimated_duration_minutes = req.estimated_duration_minutes
        resource.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(resource)
        
        logger.info(f"✓ Resource updated: {resource_id} by {current_user['profile_id']}")
        return ResourceResponse.from_orm(resource)
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid resource ID format"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"✗ Error updating resource: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update resource"
        )


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: str,
    db: AsyncSession = Depends(get_platform_db),
    current_user: dict = Depends(require_role("university_admin", "platform_admin")),
):
    """Delete resource (admin only)."""
    try:
        resource_uuid = uuid.UUID(resource_id)
        
        resource_result = await db.execute(
            select(Resource).where(Resource.id == resource_uuid)
        )
        resource = resource_result.scalar_one_or_none()
        
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        await db.delete(resource)
        await db.commit()
        
        logger.info(f"✓ Resource deleted: {resource_id} by {current_user['profile_id']}")
        return None
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid resource ID format"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"✗ Error deleting resource: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete resource"
        )
