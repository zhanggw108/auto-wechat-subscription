# PRD, AI 论文与行业热点公众号内容雷达

## 1. Summary

本产品是一个面向个人使用的 AI 论文与行业热点内容生产工作台。它持续监控近期 AI 论文、AI 行业新闻、官方博客、开源项目和社区动态，筛选出值得认真解读的论文和热点，并生成一套可审核、可排版、可复制发布到公众号的稿件包。

产品不做自动发布。它的目标是把每天选题、写稿、配图、排版这套流程压缩到 10-20 分钟，让使用者只负责判断、微调和发布。

## 2. Contacts

| Role | Owner | Comment |
| --- | --- | --- |
| Product Owner | Gary | 个人使用者，最终审核和发布负责人 |
| Content Strategy | Gary | 定义论文筛选标准、文章口吻和内容判断标准 |
| Engineering | TBD | 实现采集、筛选、生成、排版工作流 |
| Design | TBD | 实现高级感、鲜艳、动效丰富的个人工作台体验 |

## 3. Background

这个工作台的核心目标是稳定产出“专业但好读”的 AI 论文公众号内容。长文章不是泛泛的选题灵感，也不是工程项目介绍，而是近期重要 AI 论文的深度解读。

内容需要同时满足三个目标。

第一个是发现近期值得读的 AI 论文。这里的“近期高热”不死卡 24 小时或 7 天，而是指近期在研究价值、方法贡献、实验扎实度或社区讨论中明显值得关注的论文。

第二个是把论文讲清楚。文章要有公众号可读性，但判断标准以学术价值优先：问题是否重要、方法是否有新意、实验是否可信、局限是否需要警惕、为什么现在值得读。

第三个是保留 AI 行业敏感度。AI 热点、产品发布、官方博客和 GitHub 项目用于补充当天 AI 圈动态，但它们不应抢占论文深度解读的位置。

现在的问题是，AI 新闻、论文、GitHub 项目、自媒体内容每天都太多。靠人工刷平台会漏，会慢，也很难稳定形成选题资产。与此同时，纯 AI 自动生成的文章又容易有 AI 味，读起来像报告，不像一个真正懂行的人在认真分享。

所以这个产品要做的不是「全自动公众号机器」，而是「个人内容雷达 + 公众号稿件工坊」。

它负责发现、筛选、起草、配图、排版。人负责判断、润色和发布。

## 4. Objective

### Objective

构建一个个人使用的 AI 内容生产工作台，每天自动产出一套公众号候选稿件包，帮助使用者稳定发布高质量 AI 论文与行业热点内容。

### Why it matters

- 降低每日选题成本。
- 提高 AI 论文热点捕捉速度。
- 稳定产出近期重要 AI 论文的深度解读。
- 保持文章的人味和判断力，避免公众号内容过度 AI 化。
- 形成长期可复用的选题库、论文库、素材库和图片资产库。

### Key Results

| Key Result | Target |
| --- | --- |
| 每日选题包产出 | 每天 11:00 自动生成 1 套结构化 topic pack，包含 5 个长文章选题、5-10 个 AI 热点话题、5-10 篇高热 arXiv 论文 |
| 每日文章包产出 | 每天至少生成 1 套可审核公众号文章包，长文章可详细解读，热点和 arXiv 速报保持简要概述 |
| 人工审核耗时 | 单篇文章从打开稿件包到可发布不超过 20 分钟 |
| 内容相关性 | 每日主文章必须绑定具体 AI 论文或论文组，不能是泛话题或纯项目介绍 |
| 来源可追溯 | 每篇文章必须附带素材来源清单 |
| 历史可回看 | 每日自动生成和手动刷新都必须保存版本记录，支持按日期查看历史话题 |
| 发布成功率 | 人工审核后可直接复制排版发布的稿件比例不低于 70% |

## 5. Market Segments

### Primary User

个人内容生产者，也就是你本人。

你的核心任务不是管理团队，而是每天快速判断今天什么值得写，然后把它变成公众号内容。

### Jobs to Be Done

- 当我早上打开工作台时，我想马上知道今天 AI 圈有哪些值得写的热点。
- 当一篇论文突然变热或近期明显值得关注时，我想知道它解决了什么问题，是否值得写成公众号深度解读。
- 当我决定写一个选题时，我想快速拿到文章结构、素材、配图和排版稿。
- 当 AI 写得太像 AI 时，我想让它变得更像真人，有观点，有语气，有节奏。
- 当我审核文章时，我想看到证据链、风险点和可改动建议，而不是一坨生成文本。

### Constraints

- 不做自动发布，避免误发和内容风险。
- 公众号文章必须可复制到微信编辑器或公众号后台。
- 图片生成使用 `image2`，由使用者提供 API Key。
- 文章降 AI 味使用 `khazix-writer` 风格。
- 热点来源以公开 RSS、公开页面、API、GitHub、论文 API 为主，避免高风险爬虫。
- 实时信源模式必须严格可信：启用真实抓取后，任一启用信源失败就直接报错，不允许静默回退到本地样例或覆盖上一轮成功数据。

## 6. Value Propositions

### Before

每天要人工刷新闻、看论文、找 GitHub 项目、判断选题、写文章、找图、排版。流程碎，时间长，很容易被信息流拖走。

### How

产品自动抓取 AI 行业信号，按学术价值、可信度、可写性和传播可读性打分。它把最值得写的论文和热点变成版本化 topic pack，再生成公众号稿件、配图和排版稿。

### After

使用者每天打开工作台，就像打开一台 AI 内容雷达。系统已经把今天最值得写的东西推到眼前。你只需要选、审、改、发。

### Why this is better

普通 AI 写作工具只会写文章。这个产品先解决「写什么」，再解决「怎么写」，最后解决「怎么排版发布」。它不是单点工具，而是一条完整内容生产线。

## 7. Solution

### 7.1 Product Shape

产品由 6 个主要页面组成。

1. **今日雷达**
   展示当天 AI 新闻、论文、GitHub 项目、自媒体热点。核心是快速判断今天什么值得看。

2. **选题池**
   展示当天 topic pack：5 个论文深度解读候选、5-10 个 AI 热点话题、5-10 篇高热 arXiv 论文。每个条目有评分、来源、推荐文章类型、学术价值判断和去重标记。

3. **论文解析台**
   展示论文摘要、核心贡献、方法图、实验结果、代码仓库、可延伸选题。

4. **文章工坊**
   生成长文章正文、热点简报、arXiv 速报、标题候选、封面提示词、配图提示词。

5. **排版预览**
   展示公众号可复制版本，包括封面图、正文、图片、引用、来源和结尾引导。

6. **历史话题库**
   保存每天自动生成和每次手动刷新后的 topic pack 版本，方便按日期、模块、版本查看历史长文章选题、热点、arXiv 论文、提示词、LLM response id 和图片资产。

### 7.2 Daily Publishing Modules

每日 11:00 自动生成一套结构化 topic pack。topic pack 是当天内容生产的最小版本单位，固定包含 3 个模块：

1. **论文深度解读候选**
   每天生成 5 个长文章候选。每个候选必须绑定具体 AI 论文或论文组，不能由 GitHub 项目、行业新闻或泛话题单独充当。长文章需要详细解读，必须调用 LLM 生成结构和正文，并经过降 AI 味处理。配图必须调用使用者在管理端配置好的 image API，至少生成封面图和机制图；image API 未配置或失败时，长文章生成应失败并暴露错误，不能只留下 prompt 文本假装完成。

2. **AI 热点话题**
   每天生成 5-10 个 AI 热点话题。热点只需要简要概述，不展开成长文。每条需要包含来源、一句话摘要和一句判断。模型发布、产品动态、官方博客、公司动态、GitHub 项目和社区讨论都归入本模块。

3. **arXiv 高热度论文**
   每天生成 5-10 篇高热 arXiv 论文速报。每篇只需要简要概述，说明论文名、方向、核心贡献、实验亮点、适合谁读、是否值得后续展开成长文章。排序以学术价值优先，不以 GitHub 或社区传播热度为主导。

这 3 个模块共同组成当天 topic pack，并以版本形式保存。当天 11:00 自动生成完整版本；手动刷新时，使用者可以选择刷新全部，也可以只刷新其中一个模块。每次刷新都必须保留旧版本，不能覆盖历史。

#### Topic Pack Version

每次自动生成或手动刷新都创建一条版本记录。

记录内容：

- 日期。
- 版本号。
- 触发方式：`scheduled` 或 `manual`。
- 刷新模块：`all`、`long_articles`、`ai_hotspots`、`arxiv_papers`。
- 本次 LLM prompt 摘要和 response id。
- 生成时间。
- 完整 topic pack 快照。
- 去重字段：标题、URL、arXiv ID、核心实体、角度 hash。

前端必须提供历史话题入口，让使用者可以按日期查看当天所有版本，并比较手动刷新前后的变化。

#### 论文深度解读候选

长文章模块每天生成 5 个可写深的论文候选。使用者可以从中选择一篇作为主文章，也可以手动刷新长文章模块让 LLM 生成新角度。候选必须来自论文源，优先 arXiv；GitHub 项目、新闻和产品动态只能作为辅助证据或热点条目，不能单独进入长文章模块。优先级如下。

1. **近期重要 AI 论文解析**
   关注近期明显值得读的 AI 论文，不局限 Agent/RAG，覆盖 LLM、多模态、生成模型、AI safety、推理效率、训练方法、评测、AI coding、AI4Science、机器人、世界模型等方向。内容包括论文解决的问题、方法贡献、实验可信度、局限和影响。

2. **学术价值高的 AI 论文解析**
   不一定是全网最热，但必须有明确研究问题、方法新意和实验支撑。优先选择能帮助读者理解一个研究趋势或技术分歧的论文。

3. **论文组深度解读**
   当单篇论文不足以支撑文章时，可以把 2-3 篇同方向论文串成一个研究问题，但文章仍必须围绕论文贡献展开，而不是泛泛写行业趋势。

长文章生成时必须同步生成配图。MVP 至少生成封面图和 1 张机制图；后续可扩展金句图、流程图和对比图。配图走管理端配置的 image API，不允许只停留在 prompt 文本。

#### AI 热点模块

AI 热点模块用于覆盖当天 AI 行业动态，保持公众号对行业变化的敏锐度。

默认结构：

- 5-10 条 AI 热点。
- 每条包含标题、来源、一句话摘要和一句人工判断。
- 热点类型包括模型发布、AI 产品、开源项目、GitHub 趋势、公司动态、开发者生态和重要争议。
- GitHub 项目主要进入本模块，作为工具、开源实现或工程动态；只有当项目明确绑定重要论文时，才可作为论文深度解读的辅助证据。

#### arXiv 论文模块

arXiv 模块用于快速覆盖当天高热论文，让读者知道哪些论文值得加入阅读列表。

默认结构：

- 5-10 篇 arXiv 高热度文章。
- 每篇包含论文名、arXiv 链接、方向标签、核心亮点、适合谁读。
- 标记是否值得后续展开成长论文解读。
- 优先选择学术价值高、问题清楚、方法有新意、实验扎实或近期仍被研究社区讨论的论文。方向覆盖整个 AI 领域，不局限 Agent/RAG。

### 7.3 Content Workflow

1. 每天 11:00 定时抓取信源。
2. 清洗、去重、聚类。
3. 对新闻、论文、项目分别评分。
4. 构建去重上下文，包括历史 topic pack、已发布文章、当天已刷新版本。
5. 调用 LLM 生成完整 topic pack：5 个长文章、5-10 个 AI 热点、5-10 篇 arXiv 论文。
6. 校验数量、字段、来源、去重结果和学术相关度。
7. 为长文章生成详细解读，并调用 LLM 做去 AI 味改写。
8. 调用图片 API 为长文章生成封面图和机制图。
9. 生成热点和 arXiv 简要概述。
10. 保存 topic pack 版本记录、来源、证据、prompt 摘要和 LLM response id。
11. 输出公众号排版稿。
12. 使用者人工审核、按模块刷新或复制到公众号后台发布。

### 7.4 Manual Refresh

手动刷新必须支持模块级选择。

可刷新范围：

- `long_articles`：重新生成 5 个长文章候选和对应新角度。
- `ai_hotspots`：重新生成 5-10 个 AI 热点话题。
- `arxiv_papers`：重新生成 5-10 篇高热 arXiv 论文速报。
- `all`：重新生成完整 topic pack。

刷新规则：

- 每次刷新都调用 LLM，不允许只在固定候选之间切换。
- LLM 输入必须包含当天已有版本、历史已发布话题、已出现标题、URL、arXiv ID、实体和角度 hash。
- LLM 必须生成新角度，不能复用当天已经出现过的同质选题。
- 只刷新单个模块时，其它模块从上一版复制，并生成新的完整 topic pack 版本。
- 刷新失败不能覆盖上一版成功内容。

### 7.5 History and Review

历史话题库用于长期复盘与避免重复选题。

MVP 要求：

- 按日期查看 topic pack 列表。
- 查看每个日期下所有版本。
- 查看每个版本的 3 个模块内容。
- 标记某个长文章、热点或 arXiv 条目为已使用、已发布、已拒绝。
- 后续 LLM 生成和手动刷新必须读取这些状态做去重。

### 7.6 Data Sources

| Source Type | Candidate Integration |
| --- | --- |
| AI 行业新闻 | `ai-news-radar`, RSSHub, 官方博客 RSS |
| 自媒体热点 | RSSHub, TopHub, Buzzing, Hacker News, X 公开信号 |
| 论文 | arXiv API, arXiv RSS, Semantic Scholar API |
| 代码与实验材料 | GitHub Search, GitHub Trending, Papers with Code |
| 工具/产品 | Product Hunt, GitHub releases, 官方 changelog |

MVP 已接入严格实时信源边界：arXiv Atom/API、RSS/`ai-news-radar` 兼容源、GitHub Search。`--live-sources` 运行时只使用真实抓取结果；任一启用源 HTTP 失败、解析失败或返回无效内容，daily run 必须失败并暴露错误。每日自动化入口必须先执行 source gate，全部健康后才允许写入新的日报数据。GitHub Search 支持可选 `GITHUB_TOKEN`，未配置时仍可访问公开 API，但更容易触发 rate limit。

### 7.7 Article Generation

文章生成不直接一稿到底，分为 4 步。

1. **选题判断**
   判断这篇论文或热点是否有信息密度、有证据支撑，是否适合展开成专业但好读的 AI 论文解读。

2. **结构生成**
   先生成文章主线、论点、素材来源、配图需求。

3. **风格改写**
   使用 `khazix-writer` 降 AI 味，写成更像一个有见识的普通人在认真聊一件事。

4. **四层自检**
   检查禁用词、报告腔、空泛论断、AI 味、事实风险和引用来源。

### 7.8 Image Generation

图片使用 `image2`，由使用者提供 API Key。

每篇主文章默认生成 3 类图。

| Image Type | Purpose |
| --- | --- |
| 封面图 | 提升打开率，表达当天主选题 |
| 机制图 | 解释论文方法、模型结构或工作流 |
| 金句图 | 适合朋友圈、社群、文章中段视觉停顿 |

图片风格应与前端一致，高级、鲜艳、动态、有科技感。避免廉价 AI 紫色渐变，避免纯装饰图。

### 7.9 Frontend Design Direction

Reading this as: **personal AI content cockpit for one creator, with a vivid premium radar-room language, leaning toward custom Tailwind + Motion + generated visual assets.**

Design dials:

| Dial | Value | Reason |
| --- | --- | --- |
| DESIGN_VARIANCE | 8 | 个人工具可以更有个性，不必像企业后台一样保守 |
| MOTION_INTENSITY | 8 | 使用者明确希望动效丰富 |
| VISUAL_DENSITY | 6 | 内容信息量高，但不能像传统后台一样拥挤 |

#### Visual Language

- 高级感，不做普通 SaaS 灰白后台。
- 画面鲜艳丰富，但只保留一个主强调色体系。
- 推荐主方向，深色基底 + 电蓝/荧光绿/珊瑚红中的一种作为主强调色。
- 页面像一台内容雷达，不像普通表格管理器。
- 使用大面积动态视觉，热点流、论文卡片、选题得分、稿件状态都可以带轻动效。

#### Recommended Style

**Kinetic Editorial Radar**

特点：

- 深色或自动深浅主题。
- 首页有动态热点轨迹、选题能量值、今日雷达流。
- 卡片不做普通白卡，用分层玻璃、细线、发光边界和动态高亮。
- 文章工坊更像编辑器，降低动效，保证阅读和审核舒服。
- 论文解析页使用丰富图像、引用块、方法结构图。

#### Motion Principles

- 首页雷达可以有持续动效。
- 选题卡片进入视口时可以 stagger reveal。
- 点击选题进入文章工坊时使用状态转场。
- 配图生成、文章生成、评分计算要有可感知的进度反馈。
- 审核和排版页面降低动效强度，避免影响阅读。
- 必须支持 reduced motion，减少动态时保持可用。

### 7.10 Key Features

#### Feature 1, Daily Radar

展示过去 24 小时的 AI 信号。

Minimum:

- 今日热点总数。
- AI 强相关信号数。
- 来源健康状态。
- Top 5 热点。
- 按新闻、论文、项目、产品发布分类。

Future:

- 事件聚类时间线。
- 热点传播路径。
- 多源交叉验证。

#### Feature 2, Topic Pack and Module Refresh

每天的选题池不是单一候选列表，而是一个版本化 topic pack。

Minimum:

- 展示 5 个长文章选题。
- 展示 5-10 个 AI 热点话题。
- 展示 5-10 篇高热 arXiv 论文。
- 支持分别刷新长文章、AI 热点、arXiv 论文或刷新全部。
- 手动刷新后生成新版本，并保留历史版本入口。

#### Feature 3, Topic Scoring

每个候选选题有 4 个评分。

| Score | Meaning |
| --- | --- |
| Heat | 当前热度 |
| Relevance | 与 AI 论文深度解读定位相关度 |
| Writeability | 是否适合写成长文 |
| Conversion | 兼容字段，实际表示后续展开价值 |

#### Feature 4, Paper Analyzer

输入论文链接或自动选中论文后，生成：

- 论文一句话总结。
- 研究问题。
- 方法拆解。
- 实验可信度。
- 局限性。
- 代码或实验材料。
- 可延伸论文选题。
- 公众号写作角度。

#### Feature 5, Article Workshop

生成稿件包：

```text
article.md
article-wechat.html
cover.png
figures/
sources.md
review-checklist.md
```

#### Feature 6, WeChat Layout Preview

提供公众号排版预览。

Minimum:

- 成熟编辑器体验：Markdown 编辑、实时预览、保存、版本更新、复制 Markdown、复制 HTML 在同一工坊完成。
- Markdown 正文。
- 可复制 HTML。
- 图片插入位。
- 来源区。
- 审核清单。
- 保存前必须显式展示未保存状态，保存后重新生成 `article-wechat.html`。
- 不自动发布，所有复制、草稿箱或发布动作都必须由使用者主动触发。

Future:

- 对接 doocs/md 类成熟编辑器渲染内核或主题系统。
- 对接微信草稿箱。
- 一键复制富文本。
- 多模板切换。

#### Feature 7, History Topic Library

历史话题库保存每天生成和刷新后的内容资产。

MVP 要求：

- 按日期浏览历史 topic pack。
- 展示版本号、触发方式、刷新模块、生成时间。
- 展示该版本内的长文章、热点、arXiv 三个模块。
- 支持查看某个条目的来源、状态和是否已发布。
- 生成新选题时读取历史记录做去重。

#### Feature 8, Mature Markdown Editor Experience

当前排版页不能只是静态 HTML 查看器。它要像成熟公众号 Markdown 编辑器一样，让使用者在最终发布前完成最后一公里。

MVP 要求：

- 文章工坊内置三栏体验：左侧 Markdown 编辑/模块阅读，中间或右侧实时预览，旁侧保留证据、来源和审核清单。
- 支持手动编辑 `article.md`，并通过保存动作落盘。
- 保存后后端重新渲染 `article-wechat.html`，稿件版本号递增，保留历史归档。
- 支持复制 Markdown 和复制 HTML，方便进入微信后台继续人工发布。
- 实时预览用于快速确认阅读结构，正式可复制稿以服务端生成的 HTML 为准。
- 参考 [doocs/md](https://github.com/doocs/md) 的成熟编辑器体验和 WTFPL 宽松许可证边界；MVP 不直接拷贝其源码或主题，后续如接入其渲染/主题能力，需保留许可证声明并通过适配层隔离。

明确不做：

- 不引入需要商业授权的 `md2wechat-skill` 源码或主题。
- 不在每日自动任务里自动推送微信草稿箱。
- 不把编辑器预览当作事实审核结果。

### 7.11 Technology

Recommended stack:

| Layer | Recommendation |
| --- | --- |
| Frontend | Next.js or React |
| Styling | Tailwind CSS |
| Motion | Motion for React, GSAP only for complex scroll scenes |
| Backend | Python FastAPI or Node.js |
| Workflow | n8n optional, or custom scheduler |
| Database | PostgreSQL |
| Vector Search | pgvector |
| Queue | Redis + worker |
| News Source | ai-news-radar, RSSHub |
| Paper Source | arXiv API, Semantic Scholar, Papers with Code |
| Code Source | GitHub Search, later GitHub Trending/Papers with Code |
| Writing | LLM + khazix-writer |
| Image | image2 |
| Layout | 内置 Markdown to WeChat HTML fallback + doocs/md style compatibility |
| Mature Editor | React 内嵌 Markdown 编辑器，参考 doocs/md 体验，后续可接宽松许可证渲染内核 |

### 7.12 Assumptions

- 管理端配置的 LLM API 可以稳定生成结构化 JSON topic pack。
- 管理端配置的图片 API 可以稳定生成封面图和解释图。
- `khazix-writer` 的风格适合该公众号账号，后续可能需要微调成你自己的口吻。
- `ai-news-radar` 的源质量足够做行业热点初筛。
- 微信公众号最终由人工复制发布，因此无需处理自动群发合规问题。
- 论文解析需要事实核查，不能只依赖模型总结。

## 8. Release

### MVP, 2-4 weeks

Scope:

- 接入 `ai-news-radar`。
- 接入 arXiv API。
- 接入 GitHub Search，用于发现代码与实验材料信号。
- 实时信源采用严格失败语义：不做本地样例兜底，失败时直接提示错误并保留上一轮成功数据。
- 图片生成采用严格失败语义：image2 未配置、超时或返回失败时直接提示错误，不生成本地占位图覆盖成功稿件。
- 每天 11:00 自动生成 1 套版本化 topic pack：5 个长文章选题、5-10 个 AI 热点、5-10 篇高热 arXiv 论文。
- 每日生成 1 套可审核文章包：长文章可详细解读，热点和 arXiv 论文保持简要概述。
- 支持按模块手动刷新：长文章、AI 热点、arXiv 论文或全部刷新。
- 每次自动生成和手动刷新都保存历史版本，方便按日期回看历史话题。
- 手动刷新必须调用 LLM 生成新角度，并基于历史记录去重。
- 使用 `khazix-writer` 改写风格。
- 使用 `image2` 生成封面图和 1 张机制图。
- 输出 Markdown + 可复制排版稿。
- 保存素材来源和审核清单。

Out of scope:

- 自动发布公众号。
- 多人协作。
- 复杂权限系统。
- 全平台自媒体爬虫。
- 自动事实背书。

### V1

Scope:

- 论文选题资产库。
- GitHub 项目监控增强，包括 trending、release、star/fork/issue 增速。
- Papers with Code / Semantic Scholar 增强。
- 公众号排版模板管理。
- 历史文章复盘。
- 每周专题自动生成。

### V2

Scope:

- 选题表现反馈闭环。
- 文章阅读数据导入。
- 根据历史爆文自动调整选题评分。
- 品牌化视觉模板。
- 多公众号账号风格切换。

## 9. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| AI 味过重 | 使用 `khazix-writer`，并增加四层自检 |
| 论文解析不准确 | 必须保留来源和人工审核清单 |
| 图片风格不稳定 | 固定 image2 prompt 模板和风格参数 |
| 热点质量低 | 加入学术相关度和可写性评分 |
| 手动刷新只在旧题里循环 | 手动刷新必须调用 LLM，带入当天历史版本和已使用角度做去重 |
| 历史话题重复 | 保存 topic pack 版本、实体、URL、arXiv ID 和角度 hash，生成前作为去重上下文 |
| 信息源失效 | 严格实时模式直接失败并暴露错误；记录 source `last_error`，不回退本地样例，不覆盖上一轮成功数据 |
| 公众号复制排版错乱 | 输出 Markdown 和 HTML 双版本 |
| 第三方排版工具许可证不兼容 | 优先选择 WTFPL/MIT/Apache 类宽松许可证；不复制 BUSL/商业授权工具源码 |
| 动效影响使用 | 审核页降低动效，支持 reduced motion |

## 10. Open Questions

| Question | Owner | Deadline |
| --- | --- | --- |
| 手动刷新模块选择的前端交互是按钮组、下拉菜单还是分段控件 | Gary | MVP 前 |
| 公众号最终排版偏短文还是长文 | Gary | MVP 前 |
| 是否需要形成你自己的写作风格，而不是完全使用 khazix 风格 | Gary | V1 前 |
| 是否需要保存客户咨询转化数据 | Gary | V1 前 |
| 主强调色选择电蓝、荧光绿还是珊瑚红 | Gary | 视觉设计前 |
