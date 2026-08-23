from fastapi import APIRouter

from app.api.v1.cases import router as cases_router
from app.api.v1.health import router as health_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.decisions import router as decisions_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health_router)
api_router.include_router(cases_router)
api_router.include_router(webhooks_router)
api_router.include_router(decisions_router)