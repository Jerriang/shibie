from pathlib import Path
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import desc
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db
from .models import (
    AttendanceRecord,
    AttendanceSession,
    AuditLog,
    ClassGroup,
    Course,
    Device,
    Enrollment,
    ExceptionEvent,
    ExportRequest,
    FaceProfile,
    MakeUpRequest,
    ReplayNonce,
    User,
)
from .schemas import (
    CheckInIn,
    CheckInOut,
    ClassCreate,
    CourseCreate,
    DeviceCreate,
    EdgeSyncIn,
    EdgeSyncOut,
    EnrollIn,
    ExportApproveIn,
    ExportRequestIn,
    FaceRegisterIn,
    LoginIn,
    MakeUpIn,
    MakeUpReviewIn,
    ManualCheckInIn,
    ReviewIn,
    SessionCloseIn,
    SessionCreate,
    TokenOut,
    UserCreate,
    UserOut,
)
from .security import (
    chain_hash,
    create_access_token,
    hash_password,
    require_roles,
    verify_device_signature,
    verify_password,
)
from .services.attendance import decide_status, is_duplicate, is_late, select_absent_students
from .services.audit import AuditChainRow, verify_chain
from .services.rate_limit import SlidingWindowRateLimiter
from .api.auth import router as auth_router
from .api.audit import router as audit_router
from .api.system import router as system_router

app = FastAPI(title="智能课堂人脸签到系统 API", version="1.0.0")
Base.metadata.create_all(bind=engine)
checkin_limiter = SlidingWindowRateLimiter(settings.checkin_rate_limit_per_minute)
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


app.include_router(system_router)
app.include_router(auth_router)
app.include_router(audit_router)


def log_action(
    db: Session,
    action: str,
    target_type: str,
    target_id: str,
    operator_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
):
    now_dt = datetime.now(UTC).replace(tzinfo=None)
    now = now_dt.isoformat()
    last = db.query(AuditLog).order_by(desc(AuditLog.id)).first()
    prev_hash = last.self_hash if last else None
    self_hash = chain_hash(prev_hash, action, target_type, target_id, operator_id, now)
    db.add(
        AuditLog(
            operator_id=operator_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            old_value=old_value,
            new_value=new_value,
            prev_hash=prev_hash,
            self_hash=self_hash,
            created_at=now_dt,
        )
    )




@app.post("/users", response_model=UserOut)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    user = User(
        role=payload.role,
        name=payload.name,
        student_no=payload.student_no,
        class_id=payload.class_id,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    log_action(db, "create_user", "user", str(user.id), None, None, payload.model_dump_json(exclude={"password"}))
    db.commit()
    db.refresh(user)
    return user


@app.post("/classes")
def create_class(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("admin")),
):
    cg = ClassGroup(**payload.model_dump())
    db.add(cg)
    db.flush()
    log_action(db, "create_class", "class_group", str(cg.id), current.id, None, payload.model_dump_json())
    db.commit()
    return {"id": cg.id}


@app.post("/classes/enroll")
def enroll_students(
    payload: EnrollIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("admin")),
):
    created = 0
    for sid in payload.student_ids:
        exists = (
            db.query(Enrollment)
            .filter(Enrollment.class_group_id == payload.class_group_id, Enrollment.student_id == sid)
            .first()
        )
        if not exists:
            db.add(Enrollment(class_group_id=payload.class_group_id, student_id=sid))
            created += 1
    log_action(db, "enroll_students", "class_group", str(payload.class_group_id), current.id, None, str(created))
    db.commit()
    return {"created": created}


@app.post("/devices")
def register_device(
    payload: DeviceCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("admin")),
):
    device = Device(**payload.model_dump())
    db.add(device)
    db.flush()
    log_action(db, "register_device", "device", payload.device_id, current.id, None, payload.classroom_id)
    db.commit()
    return {"id": device.id}


@app.post("/face/register")
def register_face(
    payload: FaceRegisterIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("student", "admin")),
):
    if current.role == "student" and current.id != payload.user_id:
        raise HTTPException(status_code=403, detail="学生只能注册自己的人脸")
    if not payload.consent_status:
        raise HTTPException(status_code=400, detail="必须授权后才能注册人脸")

    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    profile = db.query(FaceProfile).filter(FaceProfile.user_id == payload.user_id).first()
    if profile:
        old_version = profile.template_version
        profile.face_template = payload.face_template
        profile.quality_score = payload.quality_score
        profile.consent_status = payload.consent_status
        profile.template_version += 1
        log_action(
            db,
            "update_face_profile",
            "face_profile",
            str(payload.user_id),
            current.id,
            str(old_version),
            str(profile.template_version),
        )
    else:
        db.add(FaceProfile(**payload.model_dump()))
        log_action(db, "create_face_profile", "face_profile", str(payload.user_id), current.id, None, "1")

    db.commit()
    return {"ok": True}


@app.delete("/face/profile/{user_id}")
def delete_face_profile(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("student", "admin")),
):
    if current.role == "student" and current.id != user_id:
        raise HTTPException(status_code=403, detail="学生只能删除自己的人脸")

    profile = db.query(FaceProfile).filter(FaceProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="人脸档案不存在")

    db.delete(profile)
    log_action(db, "delete_face_profile", "face_profile", str(user_id), current.id, "exists", "deleted")
    db.commit()
    return {"ok": True}


@app.post("/courses")
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("admin")),
):
    teacher = db.get(User, payload.teacher_id)
    if not teacher or teacher.role != "teacher":
        raise HTTPException(status_code=400, detail="teacher_id 非法")
    course = Course(**payload.model_dump())
    db.add(course)
    db.flush()
    log_action(db, "create_course", "course", str(course.id), current.id, None, payload.model_dump_json())
    db.commit()
    return {"id": course.id}


@app.post("/sessions")
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("teacher", "admin")),
):
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="结束时间必须大于开始时间")
    session = AttendanceSession(**payload.model_dump())
    db.add(session)
    db.flush()
    log_action(db, "create_session", "attendance_session", str(session.id), current.id, None, payload.model_dump_json())
    db.commit()
    return {"id": session.id}


@app.post("/checkin", response_model=CheckInOut)
def check_in(payload: CheckInIn, db: Session = Depends(get_db)):
    if db.query(ReplayNonce).filter(ReplayNonce.nonce == payload.nonce).first():
        raise HTTPException(status_code=409, detail="重复请求，疑似重放")

    session = db.get(AttendanceSession, payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="签到场次不存在")
    if session.status != "open":
        raise HTTPException(status_code=400, detail="签到场次未开启")

    device = db.query(Device).filter(Device.device_id == payload.source_device_id, Device.status == "active").first()
    if not device:
        raise HTTPException(status_code=403, detail="未注册设备")
    if device.classroom_id != session.classroom_id:
        raise HTTPException(status_code=403, detail="设备教室不匹配")

    if not verify_device_signature(
        secret=device.shared_secret,
        session_id=payload.session_id,
        user_id=payload.user_id,
        nonce=payload.nonce,
        ts=payload.ts,
        signature=payload.signature,
    ):
        raise HTTPException(status_code=401, detail="设备签名校验失败")

    if not checkin_limiter.allow(payload.source_device_id):
        raise HTTPException(status_code=429, detail="签到请求过于频繁")

    db.add(ReplayNonce(nonce=payload.nonce))
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    status, reason = decide_status(payload.similarity, payload.liveness_score, payload.quality_score)
    now = datetime.now(UTC).replace(tzinfo=None)

    last_record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == payload.session_id, AttendanceRecord.user_id == payload.user_id)
        .order_by(desc(AttendanceRecord.recognized_at))
        .first()
    )

    if is_duplicate(last_record.recognized_at if last_record else None, now):
        status = "duplicate"
        reason = "5 分钟内重复签到"

    if status == "present" and is_late(now, session.start_time, session.late_threshold_minutes):
        status = "late"
        reason = "超出迟到阈值"

    db.add(
        AttendanceRecord(
            session_id=payload.session_id,
            user_id=payload.user_id,
            status=status,
            confidence=payload.similarity,
            liveness_score=payload.liveness_score,
            quality_score=payload.quality_score,
            source_device_id=payload.source_device_id,
            source_type="face",
            review_status="pending" if status == "pending_review" else "auto",
            recognized_at=now,
        )
    )

    if status in {"liveness_failed", "duplicate", "recognition_failed"}:
        db.add(ExceptionEvent(session_id=payload.session_id, type=status, detail=reason, image_ref=None))

    log_action(db, "check_in", "attendance_record", f"{payload.session_id}:{payload.user_id}", payload.user_id, None, status)
    db.commit()
    return CheckInOut(status=status, reason=reason)


@app.post("/edge/sync-checkins", response_model=EdgeSyncOut)
def edge_sync_checkins(payload: EdgeSyncIn, db: Session = Depends(get_db)):
    accepted = 0
    failed = 0
    details = []
    for event in payload.events:
        try:
            out = check_in(event, db)
            accepted += 1
            details.append({"user_id": event.user_id, "status": out.status, "reason": out.reason})
        except HTTPException as exc:
            failed += 1
            details.append({"user_id": event.user_id, "status": "failed", "reason": exc.detail})

    return EdgeSyncOut(accepted=accepted, failed=failed, details=details)




@app.post("/manual-checkin", response_model=CheckInOut)
def manual_checkin(
    payload: ManualCheckInIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("teacher", "admin")),
):
    session = db.get(AttendanceSession, payload.session_id)
    if not session or session.status != "open":
        raise HTTPException(status_code=400, detail="签到场次不可用")

    db.add(
        AttendanceRecord(
            session_id=payload.session_id,
            user_id=payload.user_id,
            status="present",
            source_type=payload.method,
            source_device_id="manual",
            confidence=1,
            liveness_score=1,
            quality_score=1,
            review_status="approved",
        )
    )
    log_action(db, "manual_checkin", "attendance_record", f"{payload.session_id}:{payload.user_id}", current.id, None, payload.reason)
    db.commit()
    return CheckInOut(status="present", reason=f"非人脸补充签到({payload.method})")


@app.post("/teacher/review")
def teacher_review(
    payload: ReviewIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("teacher", "admin")),
):
    record = db.get(AttendanceRecord, payload.record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    old = record.status
    record.status = "present" if payload.approve else "absent"
    record.review_status = "approved" if payload.approve else "rejected"

    log_action(db, "teacher_review", "attendance_record", str(record.id), current.id, old, record.status)
    db.commit()
    return {"ok": True, "status": record.status}


@app.post("/makeup/request")
def create_makeup(
    payload: MakeUpIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("student", "admin")),
):
    if current.role == "student" and current.id != payload.user_id:
        raise HTTPException(status_code=403, detail="学生只能为自己申请")

    req = MakeUpRequest(**payload.model_dump())
    db.add(req)
    db.flush()
    log_action(db, "makeup_request", "make_up_request", str(req.id), current.id, None, payload.model_dump_json())
    db.commit()
    return {"id": req.id, "status": req.status}


@app.post("/makeup/review")
def review_makeup(
    payload: MakeUpReviewIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("teacher", "admin")),
):
    req = db.get(MakeUpRequest, payload.request_id)
    if not req:
        raise HTTPException(status_code=404, detail="补签申请不存在")

    old_status = req.status
    req.status = "approved" if payload.approve else "rejected"
    req.reviewed_by = current.id
    req.reviewed_at = datetime.now(UTC).replace(tzinfo=None)

    rec = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == req.session_id, AttendanceRecord.user_id == req.user_id)
        .order_by(desc(AttendanceRecord.recognized_at))
        .first()
    )
    if rec and payload.approve:
        rec.status = "present"
        rec.review_status = "approved"

    log_action(db, "makeup_review", "make_up_request", str(req.id), current.id, old_status, req.status)
    db.commit()
    return {"ok": True, "status": req.status}


@app.post("/sessions/close")
def close_session(
    payload: SessionCloseIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("teacher", "admin")),
):
    session = db.get(AttendanceSession, payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="签到场次不存在")

    signed = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == payload.session_id).all()
    signed_ids = [r.user_id for r in signed if r.status in {"present", "late"}]

    student_ids = payload.student_ids
    if not student_ids:
        course = db.get(Course, session.course_id)
        if course and course.class_group_id:
            enrolled = db.query(Enrollment).filter(Enrollment.class_group_id == course.class_group_id).all()
            student_ids = [e.student_id for e in enrolled]

    if not student_ids:
        raise HTTPException(status_code=400, detail="缺少班级学生名单")

    absent_ids = select_absent_students(student_ids, signed_ids)

    for sid in absent_ids:
        db.add(
            AttendanceRecord(
                session_id=payload.session_id,
                user_id=sid,
                status="absent",
                source_type="system",
                source_device_id="system",
                confidence=0,
                liveness_score=0,
                quality_score=0,
                review_status="auto",
            )
        )

    session.status = "closed"
    log_action(db, "close_session", "attendance_session", str(payload.session_id), current.id, "open", f"closed:{len(absent_ids)}")
    db.commit()
    return {"closed": True, "absent_count": len(absent_ids)}


@app.post("/exports/request")
def request_export(
    payload: ExportRequestIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("teacher", "admin", "auditor")),
):
    req = ExportRequest(requester_id=current.id, session_id=payload.session_id, reason=payload.reason)
    db.add(req)
    db.flush()
    log_action(db, "request_export", "export_request", str(req.id), current.id, None, payload.reason)
    db.commit()
    return {"request_id": req.id, "status": req.status}


@app.post("/exports/approve")
def approve_export(
    payload: ExportApproveIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles("admin")),
):
    req = db.get(ExportRequest, payload.request_id)
    if not req:
        raise HTTPException(status_code=404, detail="导出申请不存在")

    old = req.status
    req.status = "approved" if payload.approve else "rejected"
    req.approved_by = current.id
    req.approved_at = datetime.now(UTC).replace(tzinfo=None)
    log_action(db, "approve_export", "export_request", str(req.id), current.id, old, req.status)
    db.commit()
    return {"ok": True, "status": req.status}




@app.get("/reports/session/{session_id}.csv")
def export_session_report(
    session_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("teacher", "admin", "auditor")),
):
    req = db.get(ExportRequest, request_id)
    if not req or req.session_id != session_id or req.status != "approved":
        raise HTTPException(status_code=403, detail="导出申请未审批")
    records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session_id).all()

    lines = [
        "record_id,user_id,status,recognized_at,confidence,liveness_score,quality_score,source_type,review_status"
    ]
    for r in records:
        lines.append(
            f"{r.id},{r.user_id},{r.status},{r.recognized_at.isoformat()},{r.confidence:.4f},{r.liveness_score:.4f},{r.quality_score:.4f},{r.source_type},{r.review_status}"
        )
    csv_content = "\n".join(lines)

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=session_{session_id}.csv"},
    )


@app.get("/reports/session/{session_id}/summary")
def session_summary(
    session_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("teacher", "admin", "auditor")),
):
    records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session_id).all()
    total = len(records)
    if total == 0:
        return {"session_id": session_id, "total": 0}

    def count(status: str) -> int:
        return len([r for r in records if r.status == status])

    return {
        "session_id": session_id,
        "total": total,
        "present": count("present"),
        "late": count("late"),
        "absent": count("absent"),
        "pending_review": count("pending_review"),
        "liveness_failed": count("liveness_failed"),
        "manual_ratio": len([r for r in records if r.source_type != "face"]) / total,
    }

