import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AppointmentResponse(BaseModel):
    """Pydantic schema for a single calendar appointment.

    Maps directly from the Interview + Candidate join query.

    Attributes:
        id: Interview UUID primary key.
        candidate_name: Full name of the candidate.
        candidate_email: Contact email of the candidate (nullable).
        role_title: Job title being interviewed for (nullable).
        scheduled_start: Start timestamp of the interview.
        scheduled_end: End timestamp of the interview.
        status: Current interview status (e.g. scheduled, completed).
    """

    id: uuid.UUID
    candidate_name: str
    candidate_email: Optional[str]
    role_title: Optional[str]
    scheduled_start: datetime
    scheduled_end: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)
