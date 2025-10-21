"""Authentication service implementation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, status

from ..config import Settings
from ..infrastructure.database import User
from ..infrastructure.repositories.user_repo import UserRepository
from .constants import (
    ACCESS_TOKEN_TYPE,
    DEFAULT_ROLE_DESCRIPTION,
    DEFAULT_ROLE_NAME,
    REFRESH_TOKEN_TYPE,
)
from .schemas import LoginRequest, RegisterRequest, TokenResponse


class AuthService:
    """Encapsulates authentication logic including JWT handling."""

    def __init__(self, user_repo: UserRepository, settings: Settings) -> None:
        self.user_repo = user_repo
        self.settings = settings

    @property
    def _secret_key(self) -> str:
        return self.settings.fastapi.secret_key

    @property
    def _algorithm(self) -> str:
        return self.settings.fastapi.token_algorithm

    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def _verify_password(self, password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())

    def _create_token(self, *, subject: str, expires_delta: timedelta, token_type: str) -> str:
        payload = {
            "sub": subject,
            "type": token_type,
            "exp": datetime.now(tz=timezone.utc) + expires_delta,
            "iat": datetime.now(tz=timezone.utc),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_tokens(self, user: User) -> TokenResponse:
        access_expires = timedelta(minutes=self.settings.fastapi.access_token_expire_minutes)
        refresh_expires = timedelta(minutes=self.settings.fastapi.refresh_token_expire_minutes)
        access = self._create_token(
            subject=user.id,
            expires_delta=access_expires,
            token_type=ACCESS_TOKEN_TYPE,
        )
        refresh = self._create_token(
            subject=user.id,
            expires_delta=refresh_expires,
            token_type=REFRESH_TOKEN_TYPE,
        )
        return TokenResponse(access_token=access, refresh_token=refresh, expires_in=int(access_expires.total_seconds()))

    async def register_user(self, payload: RegisterRequest) -> User:
        existing = await self.user_repo.get_by_email(payload.email)
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        hashed = self._hash_password(payload.password)
        default_role = await self.user_repo.ensure_role(DEFAULT_ROLE_NAME, DEFAULT_ROLE_DESCRIPTION)
        user = await self.user_repo.create_user(
            email=payload.email,
            hashed_password=hashed,
            full_name=payload.full_name,
            roles=[default_role],
        )
        return user

    async def authenticate_user(self, payload: LoginRequest) -> User:
        user = await self.user_repo.get_by_email(payload.email)
        if not user or not self._verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
        return user

    def validate_token(self, token: str, *, expected_type: str = ACCESS_TOKEN_TYPE) -> str:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return str(payload["sub"])

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        user_id = self.validate_token(refresh_token, expected_type=REFRESH_TOKEN_TYPE)
        user = await self.user_repo.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return self.create_tokens(user)


__all__ = ["AuthService"]
