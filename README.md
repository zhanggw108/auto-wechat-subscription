# AI 论文与行业热点公众号内容雷达 MVP

本仓库实现了一个本地优先的 MVP：每天生成 AI 行业信号雷达、5-10 个候选选题，以及固定 3 个模块的可审核公众号稿件包。

## 当前能力

- FastAPI 后端：`/health`、今日雷达、来源健康、选题池、论文、稿件、任务状态和重跑接口。
- 本地 deterministic pipeline：没有外部 API Key 时也能生成完整日报，便于验证工作流；开启 `--live-sources` 后进入严格实时信源模式，只使用 arXiv/RSS/GitHub Search 抓取结果，任一启用信源失败就直接报错。
- 稿件包输出：
  - 主文章：默认待选择；用户读完选题池后点击“生成长文”才生成长论文解读和 image2 配图
  - 次文章 1：AI 热点，自动生成
  - 次文章 2：arXiv 高热度文章速报，自动生成
  - `article.md`
  - `article-wechat.html`
  - `sources.md`
  - `review-checklist.md`
  - `evidence.json`
  - `topic.md`
  - `cover.png`、`figures/mechanism.png` 和对应图片 prompt 文本，只有生成主文章长文后才输出
- React 工作台：今日雷达、选题池、文章工坊、管理端四区合一。
- 人工操作：阅读选题池后生成指定选题长文、选题选择/拒绝、标题/导语/整篇/风格/封面/机制图/HTML 重跑、标记已发布。
- 管理端：可写入 LLM 和 image2 的第三方中转站 Base URL、API Key、模型和图片参数；保存后前端只显示配置状态和 masked key。

## 安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r apps/api/requirements.txt
npm install
```

## 运行

后端：

```bash
.venv/bin/python -m uvicorn ai_radar.api:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

前端：

```bash
npm run dev --workspace apps/web -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173
```

手动生成当日日报：

```bash
PYTHONPATH=apps/api .venv/bin/python -m ai_radar.cli run-daily --date 2026-06-20 --storage-root storage
```

使用严格实时信源抓取 arXiv/RSS/GitHub Search。任一启用信源失败时命令会直接失败，不会回退到本地样例，也不会覆盖上一轮成功数据：

```bash
PYTHONPATH=apps/api .venv/bin/python -m ai_radar.cli run-daily --date 2026-06-20 --storage-root storage --live-sources
```

GitHub Search 可选配置：

```bash
export GITHUB_TOKEN="ghp_xxx"
```

未配置 token 时仍会请求公开 GitHub Search API，但更容易遇到 rate limit。

信源 URL 可用环境变量覆盖：

```bash
export AI_RADAR_ARXIV_URL="https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG&sortBy=submittedDate&sortOrder=descending&max_results=10"
export AI_RADAR_NEWS_RSS_URL="https://aihot.virxact.com/feed.xml"
export AI_RADAR_GITHUB_SEARCH_URL="https://api.github.com/search/repositories?q=topic:artificial-intelligence+language:python&sort=updated&order=desc&per_page=10"
export AI_RADAR_OFFICIAL_BLOGS_RSS_URL="https://openai.com/news/rss.xml"
```

建议先做信源冒烟检查，确认所有启用源都健康后再生成日报：

```bash
PYTHONPATH=apps/api .venv/bin/python -m ai_radar.cli check-sources --date 2026-06-20 --storage-root storage
```

输出 JSON 中 `ok` 为 `true` 才继续运行 `run-daily --live-sources`；如果为 `false`，先看每个 source 的 `last_error`。

每日 11:00 自动化使用 scheduler-safe 入口：先检查严格实时信源，全部健康后才写入当天日报。

```bash
PYTHONPATH=apps/api .venv/bin/python -m ai_radar.cli run-scheduled --date 2026-06-20 --storage-root storage --live-sources
```

本机可用 `launchd` 启用每日 11:00 任务：

```bash
mkdir -p ~/Library/LaunchAgents
cp scripts/com.ai-radar.daily.plist.example ~/Library/LaunchAgents/com.ai-radar.daily.plist
launchctl unload ~/Library/LaunchAgents/com.ai-radar.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.ai-radar.daily.plist
launchctl list | grep ai-radar
```

手动触发同一条生产路径：

```bash
scripts/run-ai-radar-daily.sh
```

## LLM / 第三方中转站配置

后端使用 Responses-compatible 请求形态。推荐在前端工作台的“管理端”写入第三方中转站配置；API Key 保存在本地 `storage/settings.local.json`，接口响应只返回 masked key，不回显明文。

也可以继续使用服务端环境变量作为 fallback：

```bash
export LLM_BASE_URL="https://your-relay.example.com/v1"
export LLM_API_KEY="replace-me"
export LLM_RESPONSES_MODEL="relay-chat-model"
export LLM_TIMEOUT_SECONDS="240"
export LLM_MAX_RETRIES="3"
```

启用后，日报文章生成和 `style` 重跑会调用：

```text
POST ${LLM_BASE_URL}/responses
Authorization: Bearer ${LLM_API_KEY}
```

请求体包含 `model`、`instructions`、`input`。如果中转站失败、未配置，或返回内容缺少来源清单，系统会回退到本地 deterministic 草稿。

image2 同样可在管理端配置；环境变量 fallback 为：

```bash
export IMAGE2_BASE_URL="https://your-image-relay.example.com/v1"
export IMAGE2_API_KEY="replace-me"
export IMAGE2_RESPONSES_MODEL="relay-image-model"
export IMAGE2_TIMEOUT_SECONDS="240"
export IMAGE2_CONNECT_TIMEOUT_SECONDS="10"
export IMAGE2_MAX_RETRIES="1"
```

图片生成不再使用本地占位图兜底。`image2` 未配置、请求超时或中转站返回失败时，封面图/机制图生成会直接失败并把错误返回给前端或 CLI；已有成功稿件和上一轮成功数据不会因此被占位图片覆盖。

## 验证

```bash
.venv/bin/python -m pytest apps/api/tests -q
npm run test --workspace apps/web -- --run
npm run build
```

## 数据和稿件位置

首次访问 `/api/radar/today` 或前端工作台会生成本地数据：

```text
storage/
  radar-db.json
  drafts/YYYY-MM-DD/<topic-slug>/
```

## 外部服务接入边界

MVP 默认仍可用本地样例源跑通基础工作台；严格实时模式和图片生成采用 fail-fast 行为，不做本地兜底覆盖。

- `ai-news-radar` / RSSHub / arXiv / GitHub Search：当前已提供 arXiv Atom、RSS parser、GitHub Search parser、source refresh、`--live-sources` CLI 入口；严格实时模式下任一启用信源失败会直接报错。
- `khazix-writer`：替换 `DailyPipeline.regenerate_draft(..., stage="style")` 和正文生成步骤。
- `LLM Responses`：已提供 `ResponsesLLMProvider`；配置 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_RESPONSES_MODEL` 后会用于文章生成和风格重写。
- `image2`：已提供 Responses-compatible `Image2Provider`；配置 `IMAGE2_BASE_URL`、`IMAGE2_API_KEY`、`IMAGE2_RESPONSES_MODEL` 后会真实调用。未配置或调用失败会直接报错，不生成本地占位 PNG。
- PostgreSQL/Redis/Worker：当前 `JsonStore` 和同步 pipeline 是 MVP 本地形态，接口边界已按架构文档保留。

## MVP 限制

- 不自动发布公众号。
- 不做多人协作、权限系统或复杂爬虫。
- 当前内容生成是可审的本地草稿，不代表事实已自动核验完成。
- 未配置或调用失败的 image2 会直接提示失败，真实封面和机制图必须由 image2 provider 成功生成。
- 当前选题聚类和评分仍是轻量规则系统，不是完整向量聚类或历史反馈模型。
