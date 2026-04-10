from datetime import datetime

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    student_no: str | None = None
    user_id: int | None = None
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    role: str
    name: str
    password: str = Field(min_length=6)
    student_no: str | None = None
    class_id: str | None = None


class UserOut(BaseModel):
    id: int
    role: str
    name: str
    student_no: str | None = None
    class_id: str | None = None

    class Config:
        from_attributes = True


class ClassCreate(BaseModel):
    name: str
    department: str = ""


class EnrollIn(BaseModel):
    class_group_id: int
    student_ids: list[int]


class DeviceCreate(BaseModel):
    device_id: str
    classroom_id: str
    shared_secret: str = Field(min_length=8)


class FaceRegisterIn(BaseModel):
    user_id: int
    face_template: str = Field(min_length=16)
    quality_score: float = Field(ge=0, le=1)
    consent_status: bool


class CourseCreate(BaseModel):
    course_name: str
    teacher_id: int
    class_group_id: int | None = None
    semester: str


class SessionCreate(BaseModel):
    course_id: int
    classroom_id: str
    start_time: datetime
    end_time: datetime
    late_threshold_minutes: int = 10


class CheckInIn(BaseModel):
    session_id: int
    user_id: int
    similarity: float = Field(ge=0, le=1)
    liveness_score: float = Field(ge=0, le=1)
    quality_score: float = Field(ge=0, le=1)
    source_device_id: str
    nonce: str
    ts: int
    signature: str


class ManualCheckInIn(BaseModel):
    session_id: int
    user_id: int
    method: str = Field(pattern="^(card|qrcode|manual)$")
    reason: str


class CheckInOut(BaseModel):
    status: str
    reason: str


class ReviewIn(BaseModel):
    record_id: int
    approve: bool


class MakeUpIn(BaseModel):
    user_id: int
    session_id: int
    reason: str
    attachment_ref: str | None = None


class MakeUpReviewIn(BaseModel):
    request_id: int
    approve: bool


class SessionCloseIn(BaseModel):
    session_id: int
    student_ids: list[int] | None = None


class ExportRequestIn(BaseModel):
    session_id: int
    reason: str


class ExportApproveIn(BaseModel):
    request_id: int
    approve: bool


class EdgeSyncIn(BaseModel):
    device_id: str
    events: list[CheckInIn]


class EdgeSyncOut(BaseModel):
    accepted: int
    failed: int
    details: list[dict]
