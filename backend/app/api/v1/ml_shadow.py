from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_database_session
from app.schemas.ml_shadow import (
    MLShadowDecisionResponse,
    MLShadowSummaryResponse,
)
from app.services.ml_shadow_query_service import (
    get_ml_shadow_summary,
    list_ml_shadow_decisions,
)


router = APIRouter(
    prefix="/ml-shadow",
    tags=["ML Shadow"],
)


@router.get(
    "/summary",
    response_model=MLShadowSummaryResponse,
)
def read_ml_shadow_summary(
    tenant_id: UUID = Query(...),
    database: Session = Depends(
        get_database_session
    ),
) -> MLShadowSummaryResponse:
    result = get_ml_shadow_summary(
        database=database,
        tenant_id=tenant_id,
    )

    return MLShadowSummaryResponse(**result)


@router.get(
    "/decisions",
    response_model=list[MLShadowDecisionResponse],
)
def read_ml_shadow_decisions(
    tenant_id: UUID = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    database: Session = Depends(
        get_database_session
    ),
) -> list[MLShadowDecisionResponse]:
    results = list_ml_shadow_decisions(
        database=database,
        tenant_id=tenant_id,
        offset=offset,
        limit=limit,
    )

    return [
        MLShadowDecisionResponse(**item)
        for item in results
    ]