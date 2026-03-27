from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List


def export_attendance_csv(
    rows: Iterable[Dict],
    output_dir: str = "exports",
    class_name: str = "unknown_class",
) -> Path:
    """导出签到记录到 CSV。"""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_class = class_name.replace(" ", "_")
    output_path = out_dir / f"attendance_{safe_class}_{ts}.csv"

    fieldnames: List[str] = [
        "seat_id",
        "student_id",
        "name",
        "status",
        "checkin_time",
        "last_seen_time",
        "confidence",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    return output_path


if __name__ == "__main__":
    demo_rows = [
        {
            "seat_id": "A1",
            "student_id": "2026001",
            "name": "张三",
            "status": "present",
            "checkin_time": "2026-03-27 08:02:10",
            "last_seen_time": "2026-03-27 08:20:05",
            "confidence": 0.78,
        }
    ]
    out = export_attendance_csv(demo_rows, class_name="高三1班")
    print(f"导出完成: {out}")
