#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "[OK] dependencies installed"
echo "提示:"
echo "1) 将 yolov8n-face.pt 或 ultra_light_face_detector.onnx 放到 ./models/"
echo "2) 先运行 seat_config_gui.py 生成座位配置，再运行 face_register.py 生成人脸库"
