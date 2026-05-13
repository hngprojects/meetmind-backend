# app/api/v1/routes/candidates.py
"""Candidate endpoints."""

import math
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession
from app.core.responses import APIError, success
from app.models.interview import (
    Candidate,
    Interview,
    InterviewHighlight,
    InterviewRedFlag,
    InterviewSkillToAssess,
    InterviewSummary,
)
from app.schemas.candidate import CandidateSearchResult
from app.services.candidate import CandidateService
from app.services.interview import _get_or_create_workspace

router = APIRouter()


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


@router.get("/{candidate_id}")
async def get_candidate(
    candidate_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Get full profile for a single candidate including all interviews,
    computed stats, and AI summary data.

    GET /api/v1/candidates/{candidate_id}

    WHY UUID for candidate_id?
    UUID path parameters are validated automatically by FastAPI — if the client
    sends a non-UUID string, FastAPI returns 422 before the handler even runs.
    This prevents garbage IDs from ever hitting the database.

    WHY scalar_one_or_none() instead of fetchone()?
    scalar_one_or_none() unwraps the first column of the first row and returns
    None if there are no results, without raising an exception. It is the
    idiomatic SQLAlchemy 2.x way to fetch a single ORM object that may or
    may not exist.

    WHY order_by(Interview.scheduled_start.desc())?
    We want the most recent interview first so the frontend can display the
    latest activity at the top without doing any client-side sorting.

    WHY fetch highlights, red_flags, and skills in separate queries instead
    of using joined loads?
    Each of the three child tables has its own sort_order. Joining them in
    one query would produce a cartesian product (N highlights × M red_flags
    × K skills rows per summary), which bloats the result set and complicates
    unpacking. Three focused queries are simpler and more predictable.

    WHY .in_(summary_ids) instead of joining back to interviews?
    We already have the summary IDs in memory from step 3. Filtering by
    a small list of IDs is a single indexed lookup per table and avoids
    re-joining the interviews and summaries tables a second time.

    WHY setdefault(key, []).append()?
    This is the standard Python pattern for building a dict of lists in one
    pass. setdefault returns the existing list if the key exists, or inserts
    and returns a new empty list if it does not — no need for an if/else check.

    WHY round(..., 1) for avg_rating?
    Ratings are surfaced to users, not used in further calculations, so one
    decimal place is enough precision. Storing the raw float risks displaying
    values like 3.6666666 in the UI.
    """

    # ── 1. Candidate ──────────────────────────────────────────
    # Scope the candidate query to the current user's workspace to prevent
    # cross-workspace data leakage. _get_or_create_workspace creates a
    # default workspace if the user does not have one yet (e.g. fresh signup).
    workspace_id = await _get_or_create_workspace(db, current_user)
    result = await db.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.workspace_id == workspace_id,
        )
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise APIError(
            "Candidate not found",
            status_code=status.HTTP_404_NOT_FOUND,
            code="candidate_not_found",
        )

    # ── 2. Interviews ─────────────────────────────────────────
    result = await db.execute(
        select(Interview)
        .where(Interview.candidate_id == candidate_id)
        .order_by(Interview.scheduled_start.desc())
    )
    interviews = result.scalars().all()

    interview_ids = [i.id for i in interviews]

    # ── 3. Summaries ──────────────────────────────────────────
    summary_map = {}
    summary_ids = []
    if interview_ids:
        result = await db.execute(
            select(InterviewSummary).where(
                InterviewSummary.interview_id.in_(interview_ids)
            )
        )
        for s in result.scalars().all():
            summary_map[s.interview_id] = s
            summary_ids.append(s.id)

    # ── 4. Highlights, Red Flags, Skills ──────────────────────
    highlights_map: dict = {}
    red_flags_map: dict = {}
    skills_map: dict = {}

    if summary_ids:
        result = await db.execute(
            select(InterviewHighlight)
            .where(InterviewHighlight.summary_id.in_(summary_ids))
            .order_by(InterviewHighlight.sort_order)
        )
        for h in result.scalars().all():
            highlights_map.setdefault(h.summary_id, []).append(h)

        result = await db.execute(
            select(InterviewRedFlag)
            .where(InterviewRedFlag.summary_id.in_(summary_ids))
            .order_by(InterviewRedFlag.sort_order)
        )
        for r in result.scalars().all():
            red_flags_map.setdefault(r.summary_id, []).append(r)

        result = await db.execute(
            select(InterviewSkillToAssess)
            .where(InterviewSkillToAssess.summary_id.in_(summary_ids))
            .order_by(InterviewSkillToAssess.sort_order)
        )
        for s in result.scalars().all():
            skills_map.setdefault(s.summary_id, []).append(s)

    # ── 5. Stats ──────────────────────────────────────────────
    total = len(interviews)
    completed = sum(1 for i in interviews if i.status == "completed")
    scheduled = sum(1 for i in interviews if i.status == "scheduled")
    ratings = [i.rating for i in interviews if i.rating is not None]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

    # ── 6. Assemble ───────────────────────────────────────────
    interviews_out = []
    for interview in interviews:
        summary = summary_map.get(interview.id)
        sid = summary.id if summary else None
        interviews_out.append(
            {
                "id": str(interview.id),
                "role_title": interview.role_title,
                "status": interview.status,
                "platform": interview.platform,
                "scheduled_start": interview.scheduled_start.isoformat()
                if interview.scheduled_start
                else None,
                "duration_min": interview.duration_min,
                "rating": interview.rating,
                "questions_asked": interview.questions_asked,
                "questions_total": interview.questions_total,
                "summary": {
                    "ai_assessment": summary.ai_assessment,
                    "status": summary.status,
                    "highlights": [
                        {"content": h.content} for h in highlights_map.get(sid, [])
                    ],
                    "red_flags": [
                        {"content": r.content} for r in red_flags_map.get(sid, [])
                    ],
                    "skills_assessed": [
                        {"skill": s.skill} for s in skills_map.get(sid, [])
                    ],
                }
                if summary
                else None,
            }
        )

    return success(
        {
            "id": str(candidate.id),
            "full_name": candidate.full_name,
            "email": candidate.email,
            "phone": candidate.phone,
            "avatar_initials": candidate.avatar_initials,
            "resume_url": candidate.resume_url,
            "portfolio_url": candidate.portfolio_url,
            "stats": {
                "total_interviews": total,
                "completed": completed,
                "scheduled": scheduled,
                "average_rating": avg_rating,
            },
            "interviews": interviews_out,
        },
        message="Candidate profile retrieved",
    )
