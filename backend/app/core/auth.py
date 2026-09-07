"""JWT auth for the console/admin API. Local, no external identity
provider - fine for an internal tool, per docs/02-tech-stack.md. Passwords
are argon2-hashed; the seed script (app/seed/run.py) sets every human
agent's password to "dev-password" for local use.
"""

from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session
from app.models import HumanAgent

_ph = PasswordHasher()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # a day - a prototype console, not a bank

_security = HTTPBearer()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(agent_id: int, role: str) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(agent_id), "role": role, "exp": expires},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    session: AsyncSession = Depends(get_session),
) -> HumanAgent:
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[ALGORITHM])
        agent_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from exc

    agent = await session.get(HumanAgent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "agent not found")
    return agent


def require_admin(agent: HumanAgent = Depends(get_current_agent)) -> HumanAgent:
    if agent.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return agent
