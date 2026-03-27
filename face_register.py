from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np
from insightface.app import FaceAnalysis


def load_seat_students(seat_config_path: Path) -> Dict[str, Dict]:
    data = json.loads(seat_config_path.read_text(encoding="utf-8"))
    students = {}
    for seat in data.get("seats", []):
        sid = seat.get("student_id", "")
        name = seat.get("name", "")
        seat_id = seat.get("seat_id", "")
        students[sid] = {"name": name, "seat_id": seat_id, "student_id": sid}
    return students


def collect_images(person_dir: Path) -> List[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    return sorted([p for p in person_dir.iterdir() if p.suffix.lower() in exts])


def extract_embeddings(
    face_app: FaceAnalysis,
    image_paths: List[Path],
) -> List[np.ndarray]:
    embeds: List[np.ndarray] = []
    for p in image_paths:
        img = cv2.imread(str(p))
        if img is None:
            print(f"[WARN] 读取失败: {p}")
            continue

        faces = face_app.get(img)
        if not faces:
            print(f"[WARN] 未检测到人脸: {p}")
            continue

        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        embeds.append(face.embedding.astype(np.float32))
    return embeds


def main():
    parser = argparse.ArgumentParser(description="学生人脸库录入脚本")
    parser.add_argument("--seat-config", default="seat_config.json")
    parser.add_argument("--photos-dir", default="face_photos", help="目录结构: face_photos/<student_id>/*.jpg")
    parser.add_argument("--output", default="face_db.npz")
    parser.add_argument("--ctx", type=int, default=0, help="0=GPU, -1=CPU")
    args = parser.parse_args()

    seat_config_path = Path(args.seat_config)
    students = load_seat_students(seat_config_path)
    photos_dir = Path(args.photos_dir)

    app = FaceAnalysis(name="buffalo_l")
    app.prepare(ctx_id=args.ctx, det_size=(640, 640))

    payload = []

    for student_id, info in students.items():
        person_dir = photos_dir / student_id
        if not person_dir.exists():
            print(f"[WARN] 缺少照片目录: {person_dir}")
            continue

        image_paths = collect_images(person_dir)
        if not image_paths:
            print(f"[WARN] 目录为空: {person_dir}")
            continue

        embeds = extract_embeddings(app, image_paths)
        if not embeds:
            print(f"[WARN] 未提取到有效特征: {student_id}")
            continue

        mean_embed = np.mean(np.stack(embeds, axis=0), axis=0)
        mean_embed = mean_embed / np.linalg.norm(mean_embed)

        payload.append(
            {
                "student_id": info["student_id"],
                "name": info["name"],
                "seat_id": info["seat_id"],
                "embedding": mean_embed,
                "sample_count": len(embeds),
            }
        )
        print(f"[OK] {info['name']}({student_id}) <- {len(embeds)} 张")

    if not payload:
        raise RuntimeError("没有可保存的人脸特征")

    np.savez_compressed(
        args.output,
        student_id=np.array([x["student_id"] for x in payload]),
        name=np.array([x["name"] for x in payload]),
        seat_id=np.array([x["seat_id"] for x in payload]),
        embedding=np.stack([x["embedding"] for x in payload], axis=0),
        sample_count=np.array([x["sample_count"] for x in payload], dtype=np.int32),
    )
    print(f"[DONE] 特征库已保存: {args.output}")


if __name__ == "__main__":
    main()
