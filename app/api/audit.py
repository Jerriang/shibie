from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, ExceptionEvent, User
from ..security import chain_hash, require_roles
from ..services.audit import AuditChainRow, verify_chain

router = APIRouter(tags=["audit"])


@router.get("/audit-logs/verify")
def verify_audit_chain(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "auditor")),
):
    logs = db.query(AuditLog).order_by(AuditLog.id).all()
    rows = [
        AuditChainRow(
            id=row.id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            operator_id=row.operator_id,
            created_at_iso=row.created_at.isoformat(),
            prev_hash=row.prev_hash,
            self_hash=row.self_hash,
        )
        for row in logs
    ]
    ok, broken_at = verify_chain(rows, chain_hash)
    if not ok:
        return {"ok": False, "broken_at": broken_at}
    return {"ok": True, "count": len(rows)}


@router.get("/audit-logs")
def get_audit_logs(
    limit: int = 100,
    action: str | None = None,
    target_type: str | None = None,
    operator_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "auditor")),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    if operator_id is not None:
        query = query.filter(AuditLog.operator_id == operator_id)
    if start_time:
        query = query.filter(AuditLog.created_at >= start_time)
    if end_time:
        query = query.filter(AuditLog.created_at <= end_time)

    logs = query.order_by(desc(AuditLog.created_at)).limit(limit).all()
    return [
        {
            "id": l.id,
            "operator_id": l.operator_id,
            "action": l.action,
            "target_type": l.target_type,
            "target_id": l.target_id,
            "old_value": l.old_value,
            "new_value": l.new_value,
            "prev_hash": l.prev_hash,
            "self_hash": l.self_hash,
            "created_at": l.created_at,
        }
        for l in logs
    ]


@router.get("/exceptions")
def get_exception_events(
    limit: int = 100,
    session_id: int | None = None,
    event_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "auditor", "teacher")),
):
    query = db.query(ExceptionEvent)
    if session_id is not None:
        query = query.filter(ExceptionEvent.session_id == session_id)
    if event_type:
        query = query.filter(ExceptionEvent.type == event_type)
    if start_time:
        query = query.filter(ExceptionEvent.created_at >= start_time)
    if end_time:
        query = query.filter(ExceptionEvent.created_at <= end_time)

    rows = query.order_by(desc(ExceptionEvent.created_at)).limit(limit).all()
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "type": r.type,
            "detail": r.detail,
            "image_ref": r.image_ref,
            "created_at": r.created_at,
        }
        for r in rows
    ]
