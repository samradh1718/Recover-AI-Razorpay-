from datetime import datetime, timezone

from fastapi import APIRouter
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine


router = APIRouter(
    prefix="/health",
    tags=["System"]
)


def check_database() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return "ok"

    except Exception as error:
        return "unavailable"


def check_redis() -> str:
    settings = get_settings()

    redis_client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2
    )

    try:
        redis_client.ping()
        return "ok"

    except Exception:
        return "unavailable"

    finally:
        redis_client.close()


@router.get("")
def health_check():
    settings = get_settings()

    database_status = check_database()
    redis_status = check_redis()

    overall_status = "ok"

    if database_status != "ok" or redis_status != "ok":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "service": settings.app_name,
        "environment": settings.app_env,
        "razorpay_mode": settings.razorpay_mode,
        "dependencies": {
            "database": database_status,
            "redis": redis_status
        },
        "timestamp": datetime.now(timezone.utc)
    }