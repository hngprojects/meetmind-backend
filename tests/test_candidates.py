# tests/test_candidates.py
"""
Tests for the Candidate Profile endpoint.

Endpoints under test
--------------------
GET /api/v1/candidates/{candidate_id}  — retrieve full candidate profile
GET /api/v1/candidates/search          — search candidates by name or email
GET /api/v1/candidates/export          — export candidates as CSV


Each test registers a unique user so sessions never collide across the
shared in-memory SQLite database.

Run with:
    pytest tests/test_candidates.py -v -s
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import (
    Candidate,
    Interview,
    InterviewHighlight,
    InterviewRedFlag,
    InterviewSkillToAssess,
    InterviewSummary,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

logger = logging.getLogger(__name__)

# ── URL constants ──────────────────────────────────────────────────────────────

SIGNUP_URL = "/api/v1/auth/signup"
CANDIDATES_URL = "/api/v1/candidates"
SEARCH_URL = "/api/v1/candidates/search"
EXPORT_URL = "/api/v1/candidates/export"

# ── Helpers (GET /{candidate_id}) ──────────────────────────────────────────────


def unique_user(tag: str | None = None) -> dict:
    """Return a signup payload with a guaranteed-unique email."""
    suffix = tag or uuid.uuid4().hex[:8]
    return {
        "name": "Candidate Tester",
        "email": f"candidate_{suffix}@example.com",
        "password": "SecurePass1!",
    }


async def signup_and_get_token(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    response = await client.post(SIGNUP_URL, json=user)
    assert response.status_code == 201, (
        f"Signup failed: {response.status_code} — {response.json()}"
    )
    data = response.json()["data"]
    return data["access_token"], data["id"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Helpers (search / export) ──────────────────────────────────────────────────


async def create_user_with_workspace(db_session) -> tuple[User, Workspace]:
    """Create a user and a workspace, link them as owner."""
    user = User(
        name="Test User",
        email=f"test-{uuid.uuid4()}@example.com",
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    workspace = Workspace(
        name="Test Workspace",
        created_by=user.id,
    )
    db_session.add(workspace)
    await db_session.flush()

    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )
    db_session.add(member)
    await db_session.commit()

    return user, workspace


async def create_candidate(db_session, workspace_id, full_name, email=None):
    """Create a test candidate in a workspace."""
    candidate = Candidate(
        workspace_id=workspace_id,
        full_name=full_name,
        email=email,
    )
    db_session.add(candidate)
    await db_session.commit()
    return candidate


def auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


# ── GET /candidates/{candidate_id} ─────────────────────────────────────────────


class TestGetCandidate:
    async def _seed_workspace(
        self, db_session: AsyncSession, user_id: str
    ) -> Workspace:
        """Create a workspace and add the user as a member."""
        ws = Workspace(name="Test Workspace")
        db_session.add(ws)
        await db_session.flush()
        member = WorkspaceMember(workspace_id=ws.id, user_id=uuid.UUID(user_id))
        db_session.add(member)
        await db_session.commit()
        await db_session.refresh(ws)
        return ws

    @pytest.mark.anyio
    async def test_returns_candidate_profile(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate exists in the database with all optional fields filled
        WHEN  GET /candidates/{id} is called
        THEN  the response is 200 with the full candidate profile, empty stats
        """
        token, user_id = await signup_and_get_token(client, unique_user())

        ws = await self._seed_workspace(db_session, user_id)

        candidate = Candidate(
            workspace_id=ws.id,
            full_name="Jane Doe",
            email="jane@example.com",
            phone="+1234567890",
            avatar_initials="JD",
            resume_url="https://example.com/resume.pdf",
            portfolio_url="https://example.com/portfolio",
        )
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)
        logger.info("[seed] Created candidate %s", candidate.id)

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info("[get] GET /candidates/%s → %d", candidate.id, response.status_code)

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}. Body: {body}"
        )
        data = body["data"]
        assert data["id"] == str(candidate.id)
        assert data["full_name"] == "Jane Doe"
        assert data["email"] == "jane@example.com"
        assert data["phone"] == "+1234567890"
        assert data["avatar_initials"] == "JD"
        assert data["resume_url"] == "https://example.com/resume.pdf"
        assert data["portfolio_url"] == "https://example.com/portfolio"
        assert data["stats"]["total_interviews"] == 0
        assert data["stats"]["completed"] == 0
        assert data["stats"]["scheduled"] == 0
        assert data["stats"]["average_rating"] is None
        assert data["interviews"] == []
        logger.info("[result] Candidate profile returned with correct fields  ✓")

    @pytest.mark.anyio
    async def test_returns_401_without_token(self, client: AsyncClient):
        """
        GIVEN no Authorization header
        WHEN  GET /candidates/{id} is called
        THEN  the response is 401
        """
        fake_id = str(uuid.uuid4())
        response = await client.get(f"{CANDIDATES_URL}/{fake_id}")
        logger.info("[no auth] GET /candidates/%s → %d", fake_id, response.status_code)

        assert response.status_code == 401, (
            f"Expected 401 but got {response.status_code}. Body: {response.json()}"
        )
        logger.info("[result]  Unauthenticated request correctly rejected  ✓")

    @pytest.mark.anyio
    async def test_returns_404_for_nonexistent_candidate(self, client: AsyncClient):
        """
        GIVEN a random UUID that does not exist in the database
        WHEN  GET /candidates/{id} is called
        THEN  the response is 404
        """
        token, _ = await signup_and_get_token(client, unique_user())
        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"{CANDIDATES_URL}/{fake_id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[not found] GET /candidates/%s → %d", fake_id, response.status_code
        )

        assert response.status_code == 404, (
            f"Expected 404 but got {response.status_code}. Body: {body}"
        )
        logger.info("[result]  Nonexistent candidate correctly returns 404  ✓")

    @pytest.mark.anyio
    async def test_stats_and_interviews_returned(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with multiple interviews of varying statuses and ratings
        WHEN  GET /candidates/{id} is called
        THEN  the response includes all interviews and correctly computed stats

        Expected:
            total_interviews == 3
            completed        == 2
            scheduled        == 1
            average_rating   == 4.5  (ratings: 4 + 5 = 9, 9 / 2 = 4.5)
        """
        token, user_id = await signup_and_get_token(client, unique_user())

        ws = await self._seed_workspace(db_session, user_id)

        candidate = Candidate(workspace_id=ws.id, full_name="John Smith")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)
        logger.info("[seed] Created candidate %s", candidate.id)

        base_time = datetime(2025, 6, 1, 10, 0, 0)
        interviewer_id = uuid.UUID(user_id)

        int1 = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Backend Engineer",
            status="completed",
            scheduled_start=base_time,
            duration_min=60,
            platform="zoom",
            rating=4,
            questions_asked=8,
            questions_total=10,
        )
        int2 = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Frontend Engineer",
            status="completed",
            scheduled_start=base_time,
            duration_min=45,
            platform="google_meet",
            rating=5,
            questions_asked=6,
            questions_total=6,
        )
        int3 = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="DevOps Engineer",
            status="scheduled",
            scheduled_start=base_time,
            duration_min=30,
            platform="teams",
        )
        db_session.add_all([int1, int2, int3])
        await db_session.commit()
        await db_session.refresh(int1)
        await db_session.refresh(int2)
        await db_session.refresh(int3)
        logger.info("[seed] Created 3 interviews for candidate")

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info("[get] GET /candidates/%s → %d", candidate.id, response.status_code)

        assert response.status_code == 200
        data = body["data"]
        assert data["stats"]["total_interviews"] == 3
        assert data["stats"]["completed"] == 2
        assert data["stats"]["scheduled"] == 1
        assert data["stats"]["average_rating"] == 4.5

        assert len(data["interviews"]) == 3
        role_titles = {i["role_title"] for i in data["interviews"]}
        assert role_titles == {
            "Backend Engineer",
            "Frontend Engineer",
            "DevOps Engineer",
        }
        logger.info("[result] Stats and interview list correct  ✓")

    @pytest.mark.anyio
    async def test_summary_nested_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with an interview that has a full summary
          (highlights, red flags, skills_assessed)
        WHEN  GET /candidates/{id} is called
        THEN  the response includes the nested summary data
        """
        token, user_id = await signup_and_get_token(client, unique_user())

        ws = await self._seed_workspace(db_session, user_id)

        candidate = Candidate(workspace_id=ws.id, full_name="Summary Test")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        interview = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=uuid.UUID(user_id),
            role_title="Engineer",
            status="completed",
        )
        db_session.add(interview)
        await db_session.commit()
        await db_session.refresh(interview)

        summary = InterviewSummary(
            interview_id=interview.id,
            ai_assessment="Strong technical skills",
            status="generated",
        )
        db_session.add(summary)
        await db_session.commit()
        await db_session.refresh(summary)
        logger.info("[seed] Created summary %s", summary.id)

        highlights = [
            InterviewHighlight(
                summary_id=summary.id,
                content="Great problem solver",
                sort_order=1,
            ),
            InterviewHighlight(
                summary_id=summary.id,
                content="Clear communicator",
                sort_order=2,
            ),
        ]
        red_flags = [
            InterviewRedFlag(
                summary_id=summary.id,
                content="Needs more system design practice",
                sort_order=1,
            ),
        ]
        skills = [
            InterviewSkillToAssess(summary_id=summary.id, skill="Python", sort_order=1),
            InterviewSkillToAssess(
                summary_id=summary.id, skill="FastAPI", sort_order=2
            ),
            InterviewSkillToAssess(
                summary_id=summary.id, skill="PostgreSQL", sort_order=3
            ),
        ]
        db_session.add_all(highlights + red_flags + skills)
        await db_session.commit()
        logger.info("[seed] Created highlights, red flags, and skills")

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info("[get] GET /candidates/%s → %d", candidate.id, response.status_code)

        assert response.status_code == 200
        data = body["data"]
        assert len(data["interviews"]) == 1

        interview_data = data["interviews"][0]
        assert interview_data["summary"] is not None
        assert interview_data["summary"]["ai_assessment"] == "Strong technical skills"
        assert interview_data["summary"]["status"] == "generated"
        assert len(interview_data["summary"]["highlights"]) == 2
        hl0 = interview_data["summary"]["highlights"][0]
        hl1 = interview_data["summary"]["highlights"][1]
        assert hl0["content"] == "Great problem solver"
        assert hl0["sort_order"] == 1
        assert hl1["content"] == "Clear communicator"

        assert len(interview_data["summary"]["red_flags"]) == 1
        rf0 = interview_data["summary"]["red_flags"][0]
        assert rf0["content"] == "Needs more system design practice"
        assert len(interview_data["summary"]["skills_assessed"]) == 3
        assert interview_data["summary"]["skills_assessed"][0]["skill"] == "Python"
        assert interview_data["summary"]["skills_assessed"][1]["skill"] == "FastAPI"
        assert interview_data["summary"]["skills_assessed"][2]["skill"] == "PostgreSQL"
        logger.info("[result] Nested summary data returned correctly  ✓")

    @pytest.mark.anyio
    async def test_interview_without_summary(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with an interview that has NO summary
        WHEN  GET /candidates/{id} is called
        THEN  the interview's summary field is null
        """
        token, user_id = await signup_and_get_token(client, unique_user())

        ws = await self._seed_workspace(db_session, user_id)

        candidate = Candidate(workspace_id=ws.id, full_name="No Summary")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        interview = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=uuid.UUID(user_id),
            role_title="Engineer",
            status="scheduled",
        )
        db_session.add(interview)
        await db_session.commit()

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()

        assert response.status_code == 200
        data = body["data"]
        assert len(data["interviews"]) == 1
        assert data["interviews"][0]["summary"] is None
        logger.info("[result] Interview without summary correctly yields null  ✓")

    @pytest.mark.anyio
    async def test_average_rating_is_none_when_no_completed_interviews(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with only scheduled (unrated) interviews
        WHEN  GET /candidates/{id} is called
        THEN  average_rating is None instead of 0.0
        """
        token, user_id = await signup_and_get_token(client, unique_user("rating_none"))

        ws = await self._seed_workspace(db_session, user_id)

        candidate = Candidate(workspace_id=ws.id, full_name="No Ratings")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        interview = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=uuid.UUID(user_id),
            role_title="Engineer",
            status="scheduled",
        )
        db_session.add(interview)
        await db_session.commit()

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()

        assert response.status_code == 200
        data = body["data"]
        assert data["stats"]["average_rating"] is None
        logger.info("[result] average_rating is None when no completed interviews  ✓")

    @pytest.mark.anyio
    async def test_interviews_ordered_by_scheduled_start_desc(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with multiple interviews on different dates
        WHEN  GET /candidates/{id} is called
        THEN  interviews are sorted by scheduled_start descending
        """
        token, user_id = await signup_and_get_token(client, unique_user("ordering"))

        ws = await self._seed_workspace(db_session, user_id)

        candidate = Candidate(workspace_id=ws.id, full_name="Order Test")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        interviewer_id = uuid.UUID(user_id)

        past = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Past",
            status="completed",
            scheduled_start=datetime(2025, 1, 1),
        )
        recent = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Recent",
            status="completed",
            scheduled_start=datetime(2025, 6, 15),
        )
        middle = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Middle",
            status="completed",
            scheduled_start=datetime(2025, 3, 1),
        )
        db_session.add_all([past, recent, middle])
        await db_session.commit()

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()

        assert response.status_code == 200
        data = body["data"]
        titles = [i["role_title"] for i in data["interviews"]]
        assert titles == ["Recent", "Middle", "Past"], (
            f"Expected [Recent, Middle, Past] but got {titles}"
        )
        logger.info("[result] Interviews ordered by scheduled_start desc  ✓")


# ── GET /candidates/search ─────────────────────────────────────────────────────


class TestCandidateSearch:
    @pytest.mark.anyio
    async def test_search_returns_200_with_valid_query(self, client, db_session):
        """
        A valid search query from an authenticated user returns 200.
        """
        from app.services.auth import AuthService

        user, workspace = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        response = await client.get(
            SEARCH_URL,
            params={"q": "john"},
            headers=auth_header(token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "data" in body
        assert "meta" in body

    @pytest.mark.anyio
    async def test_search_returns_401_without_token(self, client):
        """
        An unauthenticated request to search returns 401.
        """
        response = await client.get(SEARCH_URL, params={"q": "john"})
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_search_returns_422_without_query_param(self, client, db_session):
        """
        A search request missing the q parameter returns 422.
        The q parameter is required (Query(...) with min_length=1).
        """
        from app.services.auth import AuthService

        user, _ = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        response = await client.get(
            SEARCH_URL,
            headers=auth_header(token),
        )

        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_search_returns_matching_candidates_by_name(self, client, db_session):
        """
        Searching by name returns candidates whose full_name matches the query.
        """
        from app.services.auth import AuthService

        user, workspace = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        await create_candidate(db_session, workspace.id, "John Okafor", "john@test.com")
        await create_candidate(db_session, workspace.id, "Jane Doe", "jane@test.com")

        response = await client.get(
            SEARCH_URL,
            params={"q": "John"},
            headers=auth_header(token),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        names = [c["full_name"] for c in data]
        assert "John Okafor" in names
        assert "Jane Doe" not in names

    @pytest.mark.anyio
    async def test_search_is_case_insensitive(self, client, db_session):
        """
        Search for 'john' should match 'John', 'JOHN', 'john' — ilike handles this.
        """
        from app.services.auth import AuthService

        user, workspace = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        await create_candidate(db_session, workspace.id, "JOHN UPPERCASE")
        await create_candidate(db_session, workspace.id, "john lowercase")

        response = await client.get(
            SEARCH_URL,
            params={"q": "john"},
            headers=auth_header(token),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        names = [c["full_name"] for c in data]
        assert "JOHN UPPERCASE" in names
        assert "john lowercase" in names

    @pytest.mark.anyio
    async def test_search_returns_empty_list_when_no_match(self, client, db_session):
        """
        A search that matches nothing returns an empty list, not an error.
        """
        from app.services.auth import AuthService

        user, workspace = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        response = await client.get(
            SEARCH_URL,
            params={"q": "zxqwerty12345notaname"},
            headers=auth_header(token),
        )

        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.anyio
    async def test_search_pagination_meta_is_present(self, client, db_session):
        """
        Response includes pagination metadata: page, page_size, total, total_pages.
        """
        from app.services.auth import AuthService

        user, workspace = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        response = await client.get(
            SEARCH_URL,
            params={"q": "a", "page": 1, "page_size": 10},
            headers=auth_header(token),
        )

        assert response.status_code == 200
        meta = response.json()["meta"]["pagination"]
        assert "page" in meta
        assert "page_size" in meta
        assert "total" in meta
        assert "total_pages" in meta


# ── GET /candidates/export ─────────────────────────────────────────────────────


class TestCandidateExport:
    @pytest.mark.anyio
    async def test_export_returns_200_with_csv_content_type(self, client, db_session):
        """
        Export returns 200 with Content-Type: text/csv.
        """
        from app.services.auth import AuthService

        user, workspace = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        response = await client.get(
            EXPORT_URL,
            headers=auth_header(token),
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    @pytest.mark.anyio
    async def test_export_returns_401_without_token(self, client):
        """
        Unauthenticated export request returns 401.
        """
        response = await client.get(EXPORT_URL)
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_export_response_has_content_disposition_header(
        self, client, db_session
    ):
        """
        Export response includes Content-Disposition attachment header.
        This is what tells the browser to download the file.
        """
        from app.services.auth import AuthService

        user, workspace = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        response = await client.get(
            EXPORT_URL,
            headers=auth_header(token),
        )

        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
        assert "candidates_" in response.headers.get("content-disposition", "")

    @pytest.mark.anyio
    async def test_export_csv_contains_header_row(self, client, db_session):
        """
        The first line of the CSV is the column header row.
        """
        from app.services.auth import AuthService

        user, workspace = await create_user_with_workspace(db_session)
        token = await AuthService.create_access_token(user)

        response = await client.get(
            EXPORT_URL,
            headers=auth_header(token),
        )

        assert response.status_code == 200
        first_line = response.text.split("\n")[0]
        assert "full_name" in first_line
        assert "email" in first_line
