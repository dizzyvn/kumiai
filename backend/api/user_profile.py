"""User profile API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..models.database import UserProfile
from ..models.schemas import UserProfileMetadata, UpdateUserProfileRequest

router = APIRouter(prefix="/user-profile", tags=["user-profile"])


@router.get("", response_model=UserProfileMetadata)
async def get_user_profile(db: AsyncSession = Depends(get_db)):
    """Get user profile (singleton record)."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.id == "default")
    )
    profile = result.scalar_one_or_none()

    if not profile:
        # Return empty profile if not exists
        return UserProfileMetadata(
            id="default",
            avatar=None,
            description=None,
            preferences=None,
        )

    return UserProfileMetadata.from_orm(profile)


@router.post("", response_model=UserProfileMetadata)
async def update_user_profile(
    request: UpdateUserProfileRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create or update user profile (singleton record)."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.id == "default")
    )
    profile = result.scalar_one_or_none()

    if profile:
        # Update existing profile
        if request.avatar is not None:
            profile.avatar = request.avatar
        if request.description is not None:
            profile.description = request.description
        if request.preferences is not None:
            profile.preferences = request.preferences
    else:
        # Create new profile
        profile = UserProfile(
            id="default",
            avatar=request.avatar,
            description=request.description,
            preferences=request.preferences,
        )
        db.add(profile)

    await db.commit()
    await db.refresh(profile)

    return UserProfileMetadata.from_orm(profile)
