from pydantic import BaseModel, Field


class PlanChangeClassifyRequest(BaseModel):
    to_plan_id: str = Field(..., min_length=1)
