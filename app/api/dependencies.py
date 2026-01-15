"""API 의존성 (인증 등)"""

from typing import Optional
from fastapi import HTTPException, Header
from app.config import settings


async def verify_auth(authorization: Optional[str] = Header(None)) -> bool:
    """Bearer 토큰 인증"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.replace("Bearer ", "")

    if token != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return True
