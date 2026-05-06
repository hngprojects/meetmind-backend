from app.schemas.auth_schema import SignInRequest
from fastapi import APIRouter,Depends,Response
from app.api.deps import DBSession
from app.services.auth_service import sign_in_user


router = APIRouter()


@router.post("/signin")
async def signin(request: SignInRequest, db: DBSession, response: Response) -> dict[str, str]:
    result = await sign_in_user(db, request)
    
    response.set_cookie(
        key="refresh_token",
        value=result["refresh_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60
    )

    return {
        "status": "success",
        "message": "User signed in successfully",
        "access_token": result["access_token"],
        "account_state": result["account_state"]
    }