from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_database_session
from app.schemas.ai_shadow import (
    AIShadowDecisionResponse,
    AIShadowSummaryResponse,
)
from app.services.ai_shadow_query_service import (
    get_ai_shadow_summary,
    list_ai_shadow_decisions,
)


router = APIRouter(
    prefix="/ai-shadow",
    tags=["AI Shadow"],
)


@router.get(
    "/summary",
    response_model=AIShadowSummaryResponse,
)
def read_ai_shadow_summary(
    tenant_id: UUID = Query(...),
    database: Session = Depends(
        get_database_session
    ),
) -> AIShadowSummaryResponse:
    result = get_ai_shadow_summary(
        database=database,
        tenant_id=tenant_id,
    )

    return AIShadowSummaryResponse(**result)


@router.get(
    "/decisions",
    response_model=list[AIShadowDecisionResponse],
)
def read_ai_shadow_decisions(
    tenant_id: UUID = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    database: Session = Depends(
        get_database_session
    ),
) -> list[AIShadowDecisionResponse]:
    results = list_ai_shadow_decisions(
        database=database,
        tenant_id=tenant_id,
        offset=offset,
        limit=limit,
    )

    return [
        AIShadowDecisionResponse(**item)
        for item in results
    ]