# 프론트엔드와 통신할 신고 접수 데이터의 구조(Schema)를 정의하는 파일

from pydantic import BaseModel
from typing import Optional

class ReportCreate(BaseModel):
    report_type: str
    title: str
    description: str
    target_job_id: Optional[str] = None
    user_id: Optional[str] = None

class ReportResponse(BaseModel):
    id: str
    user_id: Optional[str]
    report_type: str
    target_job_id: Optional[str]
    title: str
    description: str
    status: str
    created_at: str
