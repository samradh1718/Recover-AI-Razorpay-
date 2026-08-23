from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.decisions import RecoveryDecisionResponse
from app.db.session import get_database_session
from app.services.decision_engine import (
    RecoveryCaseNotEvaluableError,
    RecoveryCaseNotFoundError,
    evaluate_recovery_case,
    list_recovery_case_decisions,
)


router = APIRouter(
    prefix="/cases",
    tags=["Recovery decisions"],
)


@router.post(
    "/{case_id}/evaluate",
    response_model=RecoveryDecisionResponse,
    status_code=status.HTTP_200_OK,
)
def evaluate_case(
    case_id: UUID,
    database: Session = Depends(get_database_session),
) -> RecoveryDecisionResponse:
    try:
        return evaluate_recovery_case(
            database=database,
            case_id=case_id,
        )
    except RecoveryCaseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except RecoveryCaseNotEvaluableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except SQLAlchemyError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to evaluate recovery case",
        ) from error


@router.get(
    "/{case_id}/decisions",
    response_model=list[RecoveryDecisionResponse],
)
def get_case_decisions(
    case_id: UUID,
    database: Session = Depends(get_database_session),
) -> list[RecoveryDecisionResponse]:
    try:
        return list_recovery_case_decisions(
            database=database,
            case_id=case_id,
        )
    except RecoveryCaseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except SQLAlchemyError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load recovery decisions",
        ) from error