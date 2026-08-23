from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.cases import (
    RecoveryCaseCreate,
    RecoveryCaseResponse
)
from app.db.session import get_database_session
from app.services.case_service import (
    create_recovery_case,
    get_recovery_case_by_id,
    get_recovery_cases
)


router = APIRouter(
    prefix="/cases",
    tags=["Recovery Cases"]
)


@router.post(
    "",
    response_model=RecoveryCaseResponse,
    status_code=status.HTTP_201_CREATED
)
def create_case(
    case_data: RecoveryCaseCreate,
    database: Session = Depends(get_database_session)
):
    try:
        return create_recovery_case(
            database=database,
            case_data=case_data
        )

    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recovery Case violates a database constraint"
        ) from error


@router.get(
    "",
    response_model=list[RecoveryCaseResponse]
)
def list_cases(
    offset: int = Query(
        default=0,
        ge=0
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100
    ),
    database: Session = Depends(get_database_session)
):
    return get_recovery_cases(
        database=database,
        offset=offset,
        limit=limit
    )


@router.get(
    "/{case_id}",
    response_model=RecoveryCaseResponse
)
def get_case(
    case_id: UUID,
    database: Session = Depends(get_database_session)
):
    recovery_case = get_recovery_case_by_id(
        database=database,
        case_id=case_id
    )

    if recovery_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery Case not found"
        )

    return recovery_case