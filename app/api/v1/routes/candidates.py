import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DBSession
from app.core.responses import success
from app.schemas.candidate import CandidateSearchResult
from app.services.candidate import CandidateService
from app.services.candidates import get_candidate_stats
from app.services.interview import _get_or_create_workspace
from app.services.workspaces import validate_workspace_membership

router = APIRouter()


@router.get("/stats")
async def fetch_candidate_stats(
    workspace_id: uuid.UUID = Query(..., description="The unique ID of the workspace"),
    db: DBSession = None,
    current_user: CurrentUser = None,
):
    """Retrieve aggregated candidate statistics for a specific workspace.

    This endpoint calculates real-time counters for the recruitment dashboard,
    including total interviews, completed sessions, and items needing attention.

    Args:
        workspace_id: The ID of the workspace to aggregate statistics for.
        db: Async database session injected by FastAPI.
        current_user: The authenticated user making the request.

    Returns:
        A standardized success envelope containing:
        - total: Total number of interviews.
        - completed: Count of finished interviews.
        - ongoing: Count of active or live sessions.
        - needs_attention: Count of failed or problematic interviews.

    Raises:
        APIError: 403 if the user is not a member of the workspace.
        APIError: 401 if the user is unauthenticated.
    """
    # Enforce multi-tenancy and workspace membership
    await validate_workspace_membership(db, workspace_id, current_user.id)

    # Execute optimized database-level aggregation
    stats = await get_candidate_stats(db, workspace_id=workspace_id)

    return success(data=stats, message="Candidate statistics fetched successfully")


@router.get("/search")
async def search_candidates(
    db: DBSession,
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, description="Search term"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
):
    """
    Search candidates by name or email.

    GET /api/v1/candidates/search?q=john&page=1&page_size=20

    WHY Query(...) with min_length=1?
    The ... means the parameter is required — FastAPI returns 422 automatically
    if it is missing. min_length=1 prevents empty string searches like ?q=
    which would match everything and is not a real search.

    WHY ge=1 on page?
    ge means "greater than or equal to". Page 0 makes no sense — pages start
    at 1. FastAPI validates this automatically and returns 422 if violated.

    WHY le=100 on page_size?
    We cap the maximum page size at 100. Without this cap, a malicious or
    careless client could send page_size=999999 and load the entire database
    into memory in one query. This is a denial-of-service protection.
    """

    # Get the user's workspace to scope the query
    # Every candidate belongs to a workspace — we never leak cross-workspace data
    workspace_id = await _get_or_create_workspace(db, current_user)

    candidates, total = await CandidateService.search(
        db=db,
        q=q,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
    )

    # Serialize SQLAlchemy ORM objects into Pydantic schemas
    # model_validate reads from ORM attributes because from_attributes=True
    # is set in CandidateSearchResult's model_config
    results = [CandidateSearchResult.model_validate(c) for c in candidates]

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return success(
        data=[r.model_dump(mode="json") for r in results],
        message=f"Found {total} candidate(s) matching '{q}'",
        meta={
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            }
        },
    )


@router.get("/export")
async def export_candidates(
    db: DBSession,
    current_user: CurrentUser,
    q: str | None = Query(default=None, description="Optional search filter"),
):

    workspace_id = await _get_or_create_workspace(db, current_user)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"candidates_{timestamp}.csv"

    # The generator is created here but NOT awaited yet
    # StreamingResponse will consume it lazily as it streams the response
    csv_generator = CandidateService.export_csv_generator(
        db=db,
        workspace_id=workspace_id,
        q=q,
    )

    return StreamingResponse(
        content=csv_generator,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )
