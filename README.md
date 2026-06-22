# AI 论文与行业热点公众号内容雷达 MVP

本仓库实现了一个本地优先的 MVP：每天生成 AI 行业信号雷达、5-10 个候选选题，以及固定 3 个模块的可审核公众号稿件包。

## 当前能力

- FastAPI 后端：`/health`、今日雷达、来源健康、选题池、论文、稿件、任务状态和重跑接口。
- 本地 deterministic pipeline：没有外部 API Key 时也能生成完整日报，便于验证工作流；开启 `--live-sources` 后会合并 arXiv/RSS 抓取结果并生成 live 选题卡。
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

尝试真实 arXiv/RSS 抓取并在失败时回退到本地样例：

```bash
PYTHONPATH=apps/api .venv/bin/python -m ai_radar.cli run-daily --date 2026-06-20 --storage-root storage --live-sources
```

## LLM / 第三方中转站配置

后端使用 Responses-compatible 请求形态。推荐在前端工作台的“管理端”写入第三方中转站配置；API Key 保存在本地 `storage/settings.local.json`，接口响应只返回 masked key，不回显明文。

也可以继续使用服务端环境变量作为 fallback：

```bash
export LLM_BASE_URL="https://your-relay.example.com/v1"
export LLM_API_KEY="replace-me"
export LLM_RESPONSES_MODEL="relay-chat-model"
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
```

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

MVP 目前用本地样例源和本地占位图片保证端到端可跑通。后续接入点：

- `ai-news-radar` / RSSHub / arXiv：当前已提供 arXiv Atom 和 RSS parser、source refresh、`--live-sources` CLI 入口；生产部署时可把来源 URL 换成真实 `ai-news-radar` / RSSHub 地址。
- `khazix-writer`：替换 `DailyPipeline.regenerate_draft(..., stage="style")` 和正文生成步骤。
- `LLM Responses`：已提供 `ResponsesLLMProvider`；配置 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_RESPONSES_MODEL` 后会用于文章生成和风格重写。
- `image2`：已提供 Responses-compatible `Image2Provider`；配置 `IMAGE2_BASE_URL`、`IMAGE2_API_KEY`、`IMAGE2_RESPONSES_MODEL` 后会真实调用，未配置时生成本地占位 PNG。
- PostgreSQL/Redis/Worker：当前 `JsonStore` 和同步 pipeline 是 MVP 本地形态，接口边界已按架构文档保留。

## MVP 限制

- 不自动发布公众号。
- 不做多人协作、权限系统或复杂爬虫。
- 当前内容生成是可审的本地草稿，不代表事实已自动核验完成。
- 未配置 image2 时图片是本地占位 PNG，真实封面和机制图需要配置 image2 provider 后生成。
- 当前选题聚类和评分仍是轻量规则系统，不是完整向量聚类或历史反馈模型。
