# 中文版全网趋势雷达 MVP

48 小时可交付的端到端 Demo：聚合多平台信号，聚类成 Event，输出趋势榜，并提供可操作的订阅流 + Sources 管理页。

## 一键启动（本地）

### 方式 A（推荐，端到端）

```bash
cd /Users/uibang001/Desktop/test/trend-radar-mvp
docker-compose up --build
```

启动后访问：
- 首页: http://localhost:8080/
- 平台管理: http://localhost:8080/sources

### 方式 B（本地开发）

```bash
cd /Users/uibang001/Desktop/test/trend-radar-mvp/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

## Seed / Mock 数据脚本

```bash
cd /Users/uibang001/Desktop/test/trend-radar-mvp/backend
python -m app.scripts.seed_mock
```

该脚本会：
1. 执行 migration
2. 跑一次 ingest + 聚类 + 排行
3. 生成当日快照

## 可分享网站部署（Render 推荐）

仓库已提供 `render.yaml`，可直接 Blueprint 一键部署：
- `trend-radar-web`：FastAPI Web 服务
- `trend-radar-db`：PostgreSQL
- `trend-radar-refresh-5m`：每 5 分钟刷新任务
- `trend-radar-digest-0800-cst`：每天 08:00（Asia/Shanghai）快照任务（对应 UTC 00:00）

### 你需要准备
1. Render 账号
2. GitHub 仓库（包含本项目代码）
3. 可选：真实平台 API Key（如 X）
4. 可选：自定义域名（用于正式分享）

### 部署步骤
1. 将代码推送到 GitHub 仓库。
2. Render -> New -> Blueprint，选择该仓库。
3. 使用仓库根目录的 `render.yaml` 创建服务。
4. 在 Render 环境变量里补充/确认：
   - `DATABASE_URL`（由 Render DB 自动注入）
   - `APP_ENV=prod`
   - `APP_TIMEZONE=Asia/Shanghai`
   - `ENABLE_INTERNAL_SCHEDULER=false`（线上用 Cron，避免重复调度）
   - 可选：`ZHIHU_HOT_RSS`、`X_TREND_RSS`、`X_BEARER_TOKEN`
5. 等待部署完成后，访问 Web URL（如 `https://xxx.onrender.com`）。

### 上线后 5 分钟验收
1. 打开 `https://<your-domain>/api/health`，应返回 `status=ok`
2. 打开首页，能看到订阅流分段
3. 在 Sources 切换某个平台 enabled/mode，首页立即变化
4. 手动触发 `POST /api/refresh` 后数据刷新
5. 检查 Render 的两个 Cron Job 是否成功执行

## MVP 范围实现状态

- [x] `/` 首页
  - [x] 平台订阅流为主（按 source 分段）
  - [x] 今日趋势 Top5（Event 摘要）
  - [x] 左侧平台筛选 + 红点新内容提示
  - [x] 按平台分段展示（Hot/New/Both）
  - [x] 立即刷新按钮（触发后端 `/api/refresh`）
- [x] `/sources` 平台管理
  - [x] icon + name + toggle
  - [x] mode（hot/new/both）
  - [x] LocalStorage 保存配置
  - [x] 立即刷新
- [x] 后端 API 打通
- [x] 5 分钟定时刷新
- [x] 每天 08:00（Asia/Shanghai）快照生成

## 数据源说明（真实 / Mock）

### 真实优先
- 36氪（RSS）
- 虎嗅（RSS）
- 少数派（RSS）
- 知乎热榜（RSSHub 路由）
- 微博热榜（JSON/HTML）
- GitHub Trending
- HuggingFace Trending
- X Trending（RSSHub 路由）

### Mock 回退
当真实抓取失败或受限时，自动回退到 Mock（同 source_id）：
- 即刻（Mock）
- B站科技（Mock）
- 种子爆发信号（Mock）

保底规则：
- 首页 Event ≥ 20
- Breaking ≥ 3
- 每个 enabled 平台 section 至少 10 条 item

## API 文档（最小稳定）

### `GET /api/sources`
返回平台配置：
- `id`
- `name`
- `enabled`
- `mode` (`hot|new|both`)
- `weight`
- `last_fetch`

### `POST /api/sources/{id}/toggle`
请求：
```json
{ "enabled": true }
```

### `POST /api/sources/{id}/mode`
请求：
```json
{ "mode": "hot" }
```

### `POST /api/refresh`
立即运行一次 ingest + 聚类 + 排行（仅 enabled sources）

### `GET /api/home`
首页聚合数据（`sections` 为主）：
```json
{
  "sections": [
    {
      "source_id": "zhihu_hot",
      "source_name": "知乎热榜",
      "mode": "hot",
      "items": [ItemCard]
    }
  ],
  "breaking": [EventCard],
  "top_events": [EventCard]
}
```

### `GET /api/platform/{source_id}`
返回单个平台频道数据：
```json
{
  "source_id": "zhihu_hot",
  "source_name": "知乎热榜",
  "enabled": true,
  "mode": "hot",
  "last_fetch": "2026-02-28T07:00:00Z",
  "items": [ItemCard]
}
```

## 目录结构

```text
trend-radar-mvp/
├── render.yaml
├── docker-compose.yml
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── migrations/
│   │   └── 001_init.sql
│   └── app/
│       ├── main.py
│       ├── api/routes.py
│       ├── core/
│       │   ├── config.py
│       │   └── scheduler.py
│       ├── db/
│       │   ├── database.py
│       │   └── repository.py
│       ├── pipeline/
│       │   ├── engine.py
│       │   ├── providers/
│       │   └── services/text_ops.py
│       └── scripts/
│           ├── seed_mock.py
│           └── run_jobs.py
└── frontend/
    └── public/
        ├── index.html
        ├── sources.html
        ├── event.html
        ├── app.js
        └── styles.css
```

## DB Schema / Migrations

见：`backend/migrations/001_init.sql`
核心表：
- `sources`
- `raw_signals`
- `events`
- `event_signal_mapping`
- `event_heat_history`
- `daily_snapshots`
- `pipeline_runs`

## Pipeline（简化版）

1. ingest（真实 Provider，失败自动 fallback mock）
2. normalize（字段清洗 + 关键词抽取）
3. dedupe（title+url 强去重；title 弱去重）
4. cluster（关键词 Jaccard ≥ 0.35）
5. 事件聚合（平台数、信号数、关键词、摘要）
6. heat_score（简化热度公式 + 权重 + 时间衰减）
7. Breaking（增速 ≥ 0.40 且平台数 ≥ 3）
8. 持久化 events + mappings + history

## 环境变量

以 `backend/.env.example` 为准。
关键变量：
- `DATABASE_URL`
- `PIPELINE_INTERVAL_MINUTES`（默认 5）
- `BREAKING_GROWTH_THRESHOLD`（默认 0.40）
- `BREAKING_MIN_SOURCE_COUNT`（默认 3）
- `APP_TIMEZONE`（默认 `Asia/Shanghai`）
- `ENABLE_INTERNAL_SCHEDULER`（本地可 `true`；线上配合 Render Cron 建议 `false`）
