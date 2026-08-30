from fastapi import APIRouter

from app.api.v1.ai_shadow import (
    router as ai_shadow_router,
)
from app.api.v1.audit_timeline import (
    router as audit_timeline_router,
)
from app.api.v1.cases import (
    router as cases_router,
)
from app.api.v1.decisions import (
    router as decisions_router,
)
from app.api.v1.health import (
    router as health_router,
)
from app.api.v1.ml_shadow import (
    router as ml_shadow_router,
)
from app.api.v1.payment_events import (
    router as payment_events_router,
)
from app.api.v1.test_checkout import (
    router as test_checkout_router,
)
from app.api.v1.webhooks import (
    router as webhooks_router,
)


api_router = APIRouter(
    prefix="/api/v1"
)

api_router.include_router(health_router)
api_router.include_router(cases_router)
api_router.include_router(webhooks_router)
api_router.include_router(decisions_router)
api_router.include_router(payment_events_router)
api_router.include_router(ai_shadow_router)
api_router.include_router(ml_shadow_router)
api_router.include_router(audit_timeline_router)
api_router.include_router(test_checkout_router)