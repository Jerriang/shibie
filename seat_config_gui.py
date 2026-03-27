from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2


@dataclass
class SeatConfig:
    seat_id: str
    student_id: str
    name: str
    roi: List[int]  # [x1, y1, x2, y2]


class SeatConfigTool:
    def __init__(self, frame):
        self.frame = frame
        self.preview = frame.copy()
        self.seats: List[SeatConfig] = []
        self.drawing = False
        self.start_pt: Optional[Tuple[int, int]] = None
        self.end_pt: Optional[Tuple[int, int]] = None

    def mouse_cb(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_pt = (x, y)
            self.end_pt = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.end_pt = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.end_pt = (x, y)
            self._finalize_roi()

    def _finalize_roi(self):
        if not self.start_pt or not self.end_pt:
            return
        x1, y1 = self.start_pt
        x2, y2 = self.end_pt
        x1, x2 = sorted([x1, x2])
        y1, y2 = sorted([y1, y2])

        if abs(x2 - x1) < 15 or abs(y2 - y1) < 15:
            print("ROI 太小，已忽略")
            return

        seat_id = input("输入座位编号 (如 A1): ").strip()
        if not seat_id:
            print("座位编号为空，已忽略")
            return

        student_id = input("输入学号: ").strip()
        name = input("输入学生姓名: ").strip()

        cfg = SeatConfig(
            seat_id=seat_id,
            student_id=student_id,
            name=name,
            roi=[x1, y1, x2, y2],
        )
        self.seats.append(cfg)
        print(f"已添加 {seat_id} -> {name}({student_id})")

    def render(self):
        canvas = self.frame.copy()

        for seat in self.seats:
            x1, y1, x2, y2 = seat.roi
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 180, 0), 2)
            cv2.putText(
                canvas,
                f"{seat.seat_id}:{seat.name}",
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 180, 0),
                2,
                cv2.LINE_AA,
            )

        if self.drawing and self.start_pt and self.end_pt:
            cv2.rectangle(canvas, self.start_pt, self.end_pt, (0, 255, 255), 2)

        tip = "Drag to add ROI | s:save q:quit u:undo"
        cv2.putText(
            canvas,
            tip,
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (40, 240, 40),
            2,
            cv2.LINE_AA,
        )
        return canvas

    def save(self, output_path: Path, class_name: str):
        data = {
            "class_name": class_name,
            "image_size": [int(self.frame.shape[1]), int(self.frame.shape[0])],
            "seats": [asdict(x) for x in self.seats],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已保存配置: {output_path}")


def read_frame(source: str):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频源: {source}")
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("无法从视频源读取画面")
    return frame


def main():
    parser = argparse.ArgumentParser(description="课堂座位 ROI 配置工具")
    parser.add_argument("--source", default="0", help="摄像头序号(如0)或RTSP地址")
    parser.add_argument("--class-name", default="高三（1）班")
    parser.add_argument("--output", default="seat_config.json")
    args = parser.parse_args()

    source = int(args.source) if args.source.isdigit() else args.source
    frame = read_frame(source)

    tool = SeatConfigTool(frame)

    win = "Seat Config"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, tool.mouse_cb)

    while True:
        cv2.imshow(win, tool.render())
        key = cv2.waitKey(20) & 0xFF
        if key == ord("q"):
            break
        if key == ord("u") and tool.seats:
            removed = tool.seats.pop()
            print(f"已撤销: {removed.seat_id}")
        if key == ord("s"):
            tool.save(Path(args.output), args.class_name)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
