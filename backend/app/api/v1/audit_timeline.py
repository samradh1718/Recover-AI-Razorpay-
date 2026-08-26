from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_database_session
from app.schemas.audit_timeline import (
    CaseAuditTimelineResponse,
)
from app.services.audit_timeline_service import (
    get_case_audit_timeline,
)


router = APIRouter(
    prefix="/cases",
    tags=["Audit Timeline"],
)


@router.get(
    "/{case_id}/timeline",
    response_model=CaseAuditTimelineResponse,
)
def read_case_audit_timeline(
    case_id: UUID,
    tenant_id: UUID = Query(...),
    database: Session = Depends(
        get_database_session
    ),
) -> CaseAuditTimelineResponse:
    try:
        result = get_case_audit_timeline(
            database=database,
            tenant_id=tenant_id,
            case_id=case_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return CaseAuditTimelineResponse(**result)