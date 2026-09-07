from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_current_agent, verify_password
from app.db.session import get_session
from app.models import HumanAgent

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: str
    full_name: str


class MeResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    agent = (
        await session.execute(select(HumanAgent).where(HumanAgent.email == body.email))
    ).scalar_one_or_none()
    if agent is None or not verify_password(body.password, agent.password_hash):
        raise HTTPException(401, "invalid credentials")

    token = create_access_token(agent.id, agent.role)
    return LoginResponse(access_token=token, role=agent.role, full_name=agent.full_name)


@router.get("/me", response_model=MeResponse)
async def me(agent: HumanAgent = Depends(get_current_agent)) -> MeResponse:
    return MeResponse(id=agent.id, email=agent.email, full_name=agent.full_name, role=agent.role)
