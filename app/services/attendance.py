from datetime import datetime, timedelta


def decide_status(
    similarity: float,
    liveness_score: float,
    quality_score: float,
    similarity_auto_pass: float = 0.85,
    similarity_review: float = 0.75,
    liveness_threshold: float = 0.6,
    quality_threshold: float = 0.5,
) -> tuple[str, str]:
    if liveness_score < liveness_threshold:
        return "liveness_failed", "活体分过低，疑似攻击"
    if quality_score < quality_threshold:
        return "recognition_failed", "图像质量过低，请重试"
    if similarity >= similarity_auto_pass:
        return "present", "自动通过"
    if similarity >= similarity_review:
        return "pending_review", "低置信度，待教师确认"
    return "recognition_failed", "相似度不足"


def is_late(recognized_at: datetime, start_time: datetime, late_threshold_minutes: int) -> bool:
    return recognized_at > start_time + timedelta(minutes=late_threshold_minutes)


def is_duplicate(last_recognized_at: datetime | None, now: datetime, duplicate_window_minutes: int = 5) -> bool:
    if not last_recognized_at:
        return False
    return now <= last_recognized_at + timedelta(minutes=duplicate_window_minutes)


def select_absent_students(all_student_ids: list[int], signed_student_ids: list[int]) -> list[int]:
    signed_set = set(signed_student_ids)
    return [sid for sid in all_student_ids if sid not in signed_set]
