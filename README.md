# 智能课堂人脸签到系统（可运行成品化后端 v0.5）

本次继续完善，补上部署与运维落地能力：**环境化数据库配置 + Docker Compose 一键拉起 + DB 健康检查 + 签名生成脚本**。

## 新增能力
- JWT + RBAC：`admin/teacher/student/auditor`
- 班级管理：`/classes`、`/classes/enroll`
- 设备管理：`/devices`（登记教室设备与共享密钥）
- 设备签名校验：`/checkin` 需携带 `ts + signature`
- 非人脸替代签到：`/manual-checkin`（card/qrcode/manual）
- 自动缺勤：`/sessions/close` 可从课程绑定班级自动拉取学生名册
- 弱网补传：`/edge/sync-checkins` 批量补传离线缓存签到事件
- 导出审批：`/exports/request` + `/exports/approve`
- 审计防篡改：`audit_logs` 记录 `prev_hash/self_hash`，支持 `/audit-logs/verify` 链路校验
- 审计检索：`/audit-logs` 支持 action/target/operator/time 条件过滤
- 异常追踪：`/exceptions` 支持按 session/type/time 查询异常事件
- 合规删除：`DELETE /face/profile/{user_id}`
- 健康检查：`/health` 包含数据库连通性

## 本地启动
```bash
export ATTENDANCE_SECRET_KEY="replace-with-long-random-key"
export CHECKIN_RATE_LIMIT_PER_MINUTE=120
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.bootstrap
uvicorn app.main:app --reload
```

## Docker Compose 启动（推荐）
```bash
cp .env.example .env
docker compose up --build
```

服务：
- API: http://127.0.0.1:8000/docs
- Postgres: 5432
- Redis: 6379
- MinIO API: 9000
- MinIO Console: 9001

## 最小联调顺序
1. `POST /auth/login` 登录管理员
2. `POST /users` 创建 teacher / student
3. `POST /classes` + `POST /classes/enroll`
4. `POST /devices` 注册教室设备
5. `POST /courses`（可绑定 class_group_id）
6. `POST /sessions`
7. `POST /face/register`
8. 调用 `/checkin`（需设备签名）或 `/manual-checkin`
9. 断网恢复后可调用 `/edge/sync-checkins` 批量补传
10. `POST /sessions/close` 生成缺勤
11. `POST /exports/request` -> `POST /exports/approve`
12. `GET /reports/session/{id}.csv?request_id=...` / `GET /audit-logs` / `GET /audit-logs/verify` / `GET /exceptions`

## /checkin 签名说明
- 待签名串：`{session_id}|{user_id}|{nonce}|{ts}`
- 算法：`HMAC-SHA256(shared_secret, message)`
- 服务端限制：
  - 时间偏差默认不超过 60 秒
  - `nonce` 不可重复
  - 设备必须已注册且教室匹配
  - 单设备签到速率限制（默认 120 次/分钟，可环境变量调整）

### 快速生成签名（脚本）
```bash
python scripts/gen_checkin_signature.py \
  --secret your_device_secret \
  --session-id 1 \
  --user-id 1001 \
  --nonce nonce-abc
```

## 注意
- 仍需接入真实识别/PAD 模型服务（ArcFace/FAISS/PAD）。
- 生产请替换 `ATTENDANCE_SECRET_KEY`、上 HTTPS、做密钥托管与数据库备份策略。


## 代码结构
- `app/api/`：路由层（`auth.py`、`audit.py`、`system.py`）
- `app/services/`：业务与安全服务（识别规则、签名、审计链、限流）
- `app/main.py`：应用装配与剩余业务路由
