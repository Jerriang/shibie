from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from attendance_export import export_attendance_csv


@dataclass
class SeatRuntime:
    seat_id: str
    student_id: str
    name: str
    roi: Tuple[int, int, int, int]
    status: str = "unknown"  # unknown/present/absent
    present_streak: int = 0
    missing_streak: int = 0
    last_seen_ts: float = 0.0
    checkin_time: Optional[str] = None
    best_confidence: float = 0.0


class FaceDetector:
    def __init__(self, model_dir: str, conf_thres: float = 0.35, iou_thres: float = 0.5):
        self.mode = "none"
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres

        self.yolo_model = None
        self.ultra_net = None
        self._init_detector(model_dir)

    def _init_detector(self, model_dir: str):
        model_path = Path(model_dir)

        yolo_weights = model_path / "yolov8n-face.pt"
        if yolo_weights.exists():
            try:
                from ultralytics import YOLO

                self.yolo_model = YOLO(str(yolo_weights))
                self.mode = "yolo"
                print(f"[INFO] 使用 YOLOv8n-face: {yolo_weights}")
                return
            except Exception as e:
                print(f"[WARN] YOLO 加载失败，回退 DNN: {e}")

        ultra_weights = model_path / "ultra_light_face_detector.onnx"
        if ultra_weights.exists():
            self.ultra_net = cv2.dnn.readNetFromONNX(str(ultra_weights))
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                self.ultra_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.ultra_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
            else:
                self.ultra_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self.ultra_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.mode = "ultra"
            print(f"[INFO] 使用 Ultra-Light DNN: {ultra_weights}")
            return

        raise FileNotFoundError(
            "未找到检测模型，请放置 models/yolov8n-face.pt 或 models/ultra_light_face_detector.onnx"
        )

    def detect(self, image_bgr: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        if self.mode == "yolo":
            return self._detect_yolo(image_bgr)
        if self.mode == "ultra":
            return self._detect_ultra(image_bgr)
        return []

    def _detect_yolo(self, image_bgr: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        results = self.yolo_model.predict(source=image_bgr, verbose=False, conf=self.conf_thres, iou=self.iou_thres)
        boxes = []
        if not results:
            return boxes
        r = results[0]
        if r.boxes is None:
            return boxes
        xyxy = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        for b, c in zip(xyxy, confs):
            x1, y1, x2, y2 = b.astype(int).tolist()
            boxes.append((x1, y1, x2, y2, float(c)))
        return boxes

    def _detect_ultra(self, image_bgr: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        h, w = image_bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(image_bgr, 1.0 / 128, (320, 240), (127, 127, 127), swapRB=True)
        self.ultra_net.setInput(blob)
        out = self.ultra_net.forward()

        boxes = []
        # 兼容常见输出: [1,1,N,7] -> [batch, class_id, conf, x1,y1,x2,y2]
        out = out.reshape(-1, 7)
        for det in out:
            conf = float(det[2])
            if conf < self.conf_thres:
                continue
            x1 = int(det[3] * w)
            y1 = int(det[4] * h)
            x2 = int(det[5] * w)
            y2 = int(det[6] * h)
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            boxes.append((x1, y1, x2, y2, conf))
        return boxes


class Recognizer:
    def __init__(self, db_path: str, ctx_id: int = 0):
        data = np.load(db_path, allow_pickle=True)
        self.student_ids = data["student_id"]
        self.names = data["name"]
        self.seat_ids = data["seat_id"]
        self.embeddings = data["embedding"].astype(np.float32)
        self.embeddings /= np.linalg.norm(self.embeddings, axis=1, keepdims=True)

        self.app = FaceAnalysis(name="buffalo_l")
        self.app.prepare(ctx_id=ctx_id, det_size=(320, 320))

    def extract_embedding(self, face_crop_bgr: np.ndarray) -> Optional[np.ndarray]:
        faces = self.app.get(face_crop_bgr)
        if not faces:
            return None
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        emb = face.embedding.astype(np.float32)
        emb /= np.linalg.norm(emb)
        return emb

    def match(self, embedding: np.ndarray, seat_id: str, threshold: float = 0.55) -> Tuple[Optional[str], float]:
        mask = self.seat_ids == seat_id
        if mask.any():
            cand_emb = self.embeddings[mask]
            cand_ids = self.student_ids[mask]
        else:
            cand_emb = self.embeddings
            cand_ids = self.student_ids

        sims = cand_emb @ embedding
        idx = int(np.argmax(sims))
        score = float(sims[idx])
        if score >= threshold:
            return str(cand_ids[idx]), score
        return None, score

    def get_name(self, student_id: str) -> str:
        idx = np.where(self.student_ids == student_id)[0]
        if len(idx) == 0:
            return "Unknown"
        return str(self.names[int(idx[0])])


def clamp_roi(roi, w, h):
    x1, y1, x2, y2 = roi
    x1 = max(0, min(w - 1, int(x1)))
    y1 = max(0, min(h - 1, int(y1)))
    x2 = max(0, min(w - 1, int(x2)))
    y2 = max(0, min(h - 1, int(y2)))
    return x1, y1, x2, y2


def status_style(status: str):
    if status == "present":
        return (0, 210, 0), "已签到"
    if status == "absent":
        return (0, 0, 230), "缺席"
    return (0, 210, 255), "检测中"


def build_runtime(seat_config_path: str) -> Tuple[str, Dict[str, SeatRuntime]]:
    data = json.loads(Path(seat_config_path).read_text(encoding="utf-8"))
    class_name = data.get("class_name", "未知班级")
    runtime: Dict[str, SeatRuntime] = {}
    for seat in data.get("seats", []):
        seat_id = seat["seat_id"]
        runtime[seat_id] = SeatRuntime(
            seat_id=seat_id,
            student_id=seat.get("student_id", ""),
            name=seat.get("name", ""),
            roi=tuple(seat["roi"]),
        )
    return class_name, runtime


def draw_panel(frame, class_name, runtime: Dict[str, SeatRuntime]):
    h, w = frame.shape[:2]
    panel_w = 360
    canvas = np.zeros((h, w + panel_w, 3), dtype=np.uint8)
    canvas[:, :w] = frame

    seats = list(runtime.values())
    present = [s for s in seats if s.status == "present"]
    absent = [s for s in seats if s.status == "absent"]
    unknown = [s for s in seats if s.status == "unknown"]

    x0 = w + 20
    y = 40
    step = 35
    cv2.putText(canvas, f"班级: {class_name}", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
    y += step
    cv2.putText(canvas, f"应到: {len(seats)} 人", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 220, 220), 2)
    y += step
    cv2.putText(canvas, f"实到: {len(present)} 人", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 220, 30), 2)
    y += step
    cv2.putText(canvas, f"缺席: {len(absent)} 人", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 30, 230), 2)
    y += step
    cv2.putText(canvas, f"检测中: {len(unknown)} 人", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 215, 255), 2)

    y += 45
    cv2.putText(canvas, "缺席名单:", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (240, 240, 240), 2)
    y += 30
    if absent:
        for s in absent[:18]:
            cv2.putText(canvas, f"- {s.name}", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (40, 40, 250), 2)
            y += 28
    else:
        cv2.putText(canvas, "(无)", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (120, 220, 120), 2)

    return canvas


def main():
    parser = argparse.ArgumentParser(description="课堂无感人脸签到系统")
    parser.add_argument("--source", default="0", help="摄像头序号(如0)或RTSP")
    parser.add_argument("--seat-config", default="seat_config.json")
    parser.add_argument("--face-db", default="face_db.npz")
    parser.add_argument("--model-dir", default="models")
    parser.add_argument("--ctx", type=int, default=0, help="0=GPU, -1=CPU")
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--process-interval", type=float, default=1.0, help="每个座位检测间隔秒")
    parser.add_argument("--present-streak", type=int, default=3)
    parser.add_argument("--missing-streak", type=int, default=10)
    parser.add_argument("--absence-grace", type=float, default=8.0, help="检测失败后宽限秒")
    args = parser.parse_args()

    class_name, runtime = build_runtime(args.seat_config)
    detector = FaceDetector(args.model_dir)
    recognizer = Recognizer(args.face_db, ctx_id=args.ctx)

    source = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频源: {source}")

    last_proc = 0.0
    fps_t0 = time.time()
    fps_count = 0
    fps_value = 0.0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        now = time.time()
        h, w = frame.shape[:2]

        if now - last_proc >= args.process_interval:
            for seat in runtime.values():
                x1, y1, x2, y2 = clamp_roi(seat.roi, w, h)
                roi = frame[y1:y2, x1:x2]
                if roi.size == 0:
                    continue

                boxes = detector.detect(roi)
                if not boxes:
                    seat.missing_streak += 1
                    seat.present_streak = 0
                    if (seat.missing_streak >= args.missing_streak) and (
                        now - seat.last_seen_ts >= args.absence_grace
                    ):
                        seat.status = "absent"
                    continue

                best = max(boxes, key=lambda x: x[4])
                bx1, by1, bx2, by2, _ = best
                crop = roi[max(by1 - 5, 0) : min(by2 + 5, roi.shape[0]), max(bx1 - 5, 0) : min(bx2 + 5, roi.shape[1])]
                emb = recognizer.extract_embedding(crop)
                if emb is None:
                    seat.missing_streak += 1
                    seat.present_streak = 0
                    continue

                matched_id, score = recognizer.match(emb, seat.seat_id, threshold=args.threshold)
                if matched_id is None:
                    seat.present_streak = 0
                    seat.missing_streak += 1
                    continue

                expected_id = seat.student_id
                if expected_id and matched_id != expected_id:
                    seat.present_streak = 0
                    seat.missing_streak += 1
                    continue

                seat.missing_streak = 0
                seat.present_streak += 1
                seat.last_seen_ts = now
                seat.best_confidence = max(seat.best_confidence, score)

                if seat.present_streak >= args.present_streak:
                    seat.status = "present"
                    if seat.checkin_time is None:
                        seat.checkin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            last_proc = now

        for seat in runtime.values():
            x1, y1, x2, y2 = clamp_roi(seat.roi, w, h)
            color, status_cn = status_style(seat.status)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{seat.seat_id} {seat.name} | {status_cn}"
            cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.56, color, 2, cv2.LINE_AA)

        fps_count += 1
        if time.time() - fps_t0 >= 1.0:
            fps_value = fps_count / (time.time() - fps_t0)
            fps_t0 = time.time()
            fps_count = 0

        cv2.putText(frame, f"FPS: {fps_value:.1f}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (120, 255, 120), 2)
        canvas = draw_panel(frame, class_name, runtime)

        cv2.imshow("Classroom Attendance", canvas)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("e"):
            rows = []
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for s in runtime.values():
                rows.append(
                    {
                        "seat_id": s.seat_id,
                        "student_id": s.student_id,
                        "name": s.name,
                        "status": s.status,
                        "checkin_time": s.checkin_time or "",
                        "last_seen_time": now_str if s.last_seen_ts > 0 else "",
                        "confidence": round(s.best_confidence, 4),
                    }
                )
            out = export_attendance_csv(rows, class_name=class_name)
            print(f"[EXPORT] {out}")

    cap.release()
    cv2.destroyAllWindows()

    rows = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for s in runtime.values():
        rows.append(
            {
                "seat_id": s.seat_id,
                "student_id": s.student_id,
                "name": s.name,
                "status": s.status,
                "checkin_time": s.checkin_time or "",
                "last_seen_time": now_str if s.last_seen_ts > 0 else "",
                "confidence": round(s.best_confidence, 4),
            }
        )
    out = export_attendance_csv(rows, class_name=class_name)
    print(f"[DONE] 退出并导出: {out}")


if __name__ == "__main__":
    main()
