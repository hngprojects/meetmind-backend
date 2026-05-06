from app.core.security import create_refresh_token, create_access_token, verify_password
from fastapi import HTTPException
from app.schemas.auth_schema import SignInRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User

async def sign_in_user(db: AsyncSession, request: SignInRequest):
    query = select(User).where(User.email == request.email)
    response = await db.execute(query)
    existing_user = response.scalar_one_or_none()
    if not existing_user or not verify_password(request.password, existing_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    access_token = create_access_token(subject=str(existing_user.id))
    refresh_token = create_refresh_token(subject=str(existing_user.id))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_state": existing_user.account_state
    }
    
