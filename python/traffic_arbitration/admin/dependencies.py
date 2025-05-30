from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from traffic_arbitration.db.connection import get_session
from dotenv import load_dotenv
from traffic_arbitration.common.logging import logger
from traffic_arbitration.common.config import config

load_dotenv()

security = HTTPBasic()
CREDS = config.get("admin_panel", {})
USERNAME = CREDS.get("user")
PASSWORD = CREDS.get("password")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    logger.info(f"Auth attempt for user: {credentials.username}")
    if credentials.username != USERNAME or credentials.password != PASSWORD:
        logger.warning("Invalid credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_db():
    with get_session() as db:
        yield db


def pwd_context_verify(password: str, hash: str) -> bool:
    """
    Verify a password against a bcrypt hash.

    Args:
        password: The plain-text password to verify.
        hash: The bcrypt hash to check against.

    Returns:
        bool: True if the password matches the hash, False otherwise.

    Raises:
        ValueError: If the hash is invalid or malformed.
    """
    try:
        password_bytes = password.encode('utf-8')
        hash_bytes = hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except ValueError:
        return False
