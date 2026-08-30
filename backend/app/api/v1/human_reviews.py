from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.human_reviews import (
    HumanReviewRecordResponse,
    HumanReviewResolutionRequest,
    HumanReviewResolutionResponse,
)
from app.db.session import get_database_session
from app.services.human_review_service import (
    HumanReviewActionNotAllowedError,
    HumanReviewAlreadyResolvedError,
    HumanReviewCaseNotFoundError,
    HumanReviewDecisionNotFoundError,
    HumanReviewNotPendingError,
    HumanReviewTenantMismatchError,
    HumanReviewVersionConflictError,
    list_case_human_reviews,
    resolve_human_review,
)
from app.workers.tasks import (
    execute_recovery_action_task,
)


router = APIRouter(
    prefix="/cases",
    tags=["Human Review"],
)


@router.post(
    "/{case_id}/human-review/resolve",
    response_model=HumanReviewResolutionResponse,
    status_code=status.HTTP_200_OK,
)
def resolve_case_human_review(
    case_id: UUID,
    request: HumanReviewResolutionRequest,
    database: Session = Depends(
        get_database_session
    ),
) -> HumanReviewResolutionResponse:
    try:
        result = resolve_human_review(
            database=database,
            case_id=case_id,
            request=request,
        )
    except (
        HumanReviewCaseNotFoundError,
        HumanReviewDecisionNotFoundError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except HumanReviewTenantMismatchError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
    except (
        HumanReviewNotPendingError,
        HumanReviewVersionConflictError,
        HumanReviewAlreadyResolvedError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except HumanReviewActionNotAllowedError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(error),
        ) from error
    except SQLAlchemyError as error:
        database.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Unable to resolve Human Review"
            ),
        ) from error

    action_queued = False

    if result.should_queue_action:
        try:
            execute_recovery_action_task.apply_async(
                args=[
                    str(result.decision.id)
                ],
                eta=(
                    result.decision.scheduled_for
                ),
            )

            action_queued = True
        except Exception as error:
            raise HTTPException(
                status_code=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                ),
                detail=(
                    "Human Review was recorded, but "
                    "the approved recovery action "
                    "could not be queued. Retry the "
                    "same request safely."
                ),
            ) from error

    return HumanReviewResolutionResponse(
        review=HumanReviewRecordResponse
        .model_validate(result.review),
        decision=result.decision,
        case_state=(
            result.recovery_case.current_state
        ),
        action_queued=action_queued,
    )


@router.get(
    "/{case_id}/human-reviews",
    response_model=list[
        HumanReviewRecordResponse
    ],
)
def get_case_human_reviews(
    case_id: UUID,
    tenant_id: UUID = Query(...),
    database: Session = Depends(
        get_database_session
    ),
) -> list[HumanReviewRecordResponse]:
    try:
        reviews = list_case_human_reviews(
            database=database,
            case_id=case_id,
            tenant_id=tenant_id,
        )
    except HumanReviewCaseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except HumanReviewTenantMismatchError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
    except SQLAlchemyError as error:
        database.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Unable to load Human Reviews"
            ),
        ) from error

    return [
        HumanReviewRecordResponse
        .model_validate(review)
        for review in reviews
    ]