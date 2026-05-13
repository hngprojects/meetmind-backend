from pydantic import BaseModel, Field


class CandidateStatsData(BaseModel):
    """Validated data payload for candidate statistics aggregation.

    Attributes:
        total: Total number of interviews in the workspace.
        completed: Count of interviews with ``completed`` status.
        ongoing: Count of interviews with ``ongoing`` or ``live`` status.
        needs_attention: Count of interviews with ``failed`` status.
    """

    total: int = Field(default=0)
    completed: int = Field(default=0)
    ongoing: int = Field(default=0)
    needs_attention: int = Field(default=0)
