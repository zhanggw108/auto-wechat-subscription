# PRD, AI 论文与行业热点公众号内容雷达

## 1. Summary

本产品是一个面向个人使用的 AI 行业内容生产工作台。它每天自动监控 AI 行业新闻、自媒体热点、高话题度论文和相关开源项目，筛选出值得写的选题，并生成一套可审核、可排版、可复制发布到公众号的稿件包。

产品不做自动发布。它的目标是把每天选题、写稿、配图、排版这套流程压缩到 10-20 分钟，让使用者只负责判断、微调和发布。

## 2. Contacts

| Role | Owner | Comment |
| --- | --- | --- |
| Product Owner | Gary | 个人使用者，最终审核和发布负责人 |
| Content Strategy | Gary | 定义公众号选题标准、文章口吻、转化目标 |
| Engineering | TBD | 实现采集、筛选、生成、排版工作流 |
| Design | TBD | 实现高级感、鲜艳、动效丰富的个人工作台体验 |

## 3. Background

你们是一家论文辅导机构，主营人工智能方向论文辅导业务。公众号内容需要同时满足两个目标。

一个是持续捕捉 AI 行业热点，让读者觉得账号足够敏锐，跟得上行业变化。

另一个是把热点转化成论文选题、研究方法、实验设计和代码复现启发，最终服务论文辅导业务。

现在的问题是，AI 新闻、论文、GitHub 项目、自媒体内容每天都太多。靠人工刷平台会漏，会慢，也很难稳定形成选题资产。与此同时，纯 AI 自动生成的文章又容易有 AI 味，读起来像报告，不像一个真正懂行的人在认真分享。

所以这个产品要做的不是「全自动公众号机器」，而是「个人内容雷达 + 公众号稿件工坊」。

它负责发现、筛选、起草、配图、排版。人负责判断、润色和发布。

## 4. Objective

### Objective

构建一个个人使用的 AI 内容生产工作台，每天自动产出一套公众号候选稿件包，帮助使用者稳定发布高质量 AI 论文与行业热点内容。

### Why it matters

- 降低每日选题成本。
- 提高 AI 论文热点捕捉速度。
- 把行业热点转化为论文辅导业务的内容资产。
- 保持文章的人味和判断力，避免公众号内容过度 AI 化。
- 形成长期可复用的选题库、论文库、素材库和图片资产库。

### Key Results

| Key Result | Target |
| --- | --- |
| 每日候选选题产出 | 每天自动生成 5-10 个候选选题 |
| 每日文章包产出 | 每天至少生成 1 套可审核公众号文章包，固定包含主文章、次文章 1、次文章 2 |
| 人工审核耗时 | 单篇文章从打开稿件包到可发布不超过 20 分钟 |
| 内容相关性 | 每日主文章与 AI 论文辅导业务强相关比例不低于 80% |
| 来源可追溯 | 每篇文章必须附带素材来源清单 |
| 发布成功率 | 人工审核后可直接复制排版发布的稿件比例不低于 70% |

## 5. Market Segments

### Primary User

个人内容生产者，也就是你本人。

你的核心任务不是管理团队，而是每天快速判断今天什么值得写，然后把它变成公众号内容。

### Jobs to Be Done

- 当我早上打开工作台时，我想马上知道今天 AI 圈有哪些值得写的热点。
- 当一篇论文突然变热时，我想知道它解决了什么问题，适合不适合写成公众号解析。
- 当我决定写一个选题时，我想快速拿到文章结构、素材、配图和排版稿。
- 当 AI 写得太像 AI 时，我想让它变得更像真人，有观点，有语气，有节奏。
- 当我审核文章时，我想看到证据链、风险点和可改动建议，而不是一坨生成文本。

### Constraints

- 不做自动发布，避免误发和内容风险。
- 公众号文章必须可复制到微信编辑器或公众号后台。
- 图片生成使用 `image2`，由使用者提供 API Key。
- 文章降 AI 味使用 `khazix-writer` 风格。
- 热点来源以公开 RSS、公开页面、API、GitHub、论文 API 为主，避免高风险爬虫。

## 6. Value Propositions

### Before

每天要人工刷新闻、看论文、找 GitHub 项目、判断选题、写文章、找图、排版。流程碎，时间长，很容易被信息流拖走。

### How

产品自动抓取 AI 行业信号，按热度、业务相关度、可写性和转化价值打分。它把最值得写的内容变成候选选题，再生成公众号 3 模块文章包、配图和排版稿。

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
   展示 5-10 个候选选题，每个选题有评分、来源、推荐文章类型和业务转化角度。

3. **论文解析台**
   展示论文摘要、核心贡献、方法图、实验结果、代码仓库、可延伸选题。

4. **文章工坊**
   生成主文章、次文章 1、次文章 2、标题候选、封面提示词、配图提示词。

5. **排版预览**
   展示公众号可复制版本，包括封面图、正文、图片、引用、来源和结尾引导。

6. **素材资产库**
   保存历史热点、论文、文章、图片、提示词、未使用选题。

### 7.2 Daily Publishing Modules

每日公众号内容固定为 3 个模块：

1. **主文章：长论文解读**
   系统默认只提供候选选题、评分、证据和阅读素材，不自动生成长文。使用者阅读选题池后，手动选择 1 篇最值得写深的 AI 论文，再生成长论文解读，并配套 `image2` 生成的封面图和解释类配图。

2. **次文章 1：AI 热点**
   汇总当天 AI 圈最值得关注的热点，重点覆盖模型发布、产品更新、开源项目、行业新闻和关键观点，不做长篇复述，而是给出简洁判断。

3. **次文章 2：arXiv 高热度文章速报**
   从当天或近 24 小时高热 arXiv 论文中筛选若干篇，输出论文名、方向、核心亮点、适合谁读，以及是否值得后续展开成长论文解读。

这 3 个模块共同组成每天可复制到公众号后台的完整稿件包。主文章承担深度和业务转化，但必须由使用者主动选择题目后生成；两个次文章承担敏锐度、信息密度和连续更新感，可自动生成。

#### 主文章，长论文解读

主文章每天由使用者从选题池里选择一篇论文做深。优先级如下。

1. **高热 AI 论文解析**
   最适合业务转化。内容包括论文解决的问题、方法亮点、实验可信度、代码可复现性、适合学生延伸的研究方向。

2. **高业务相关度 AI 论文解析**
   不一定是全网最热，但必须能自然延伸到论文选题、实验设计、复现、baseline 或创新点设计。

3. **论文选题灵感专题**
   把多篇相关论文串成一个研究方向，给出可做选题、可复现实验和潜在创新点。

主文章生成时必须同步生成 image2 配图。MVP 至少生成封面图和 1 张机制图；后续可扩展金句图、流程图和对比图。

#### 次文章 1，AI 热点

次文章 1 用于覆盖当天 AI 行业动态，保持公众号对行业变化的敏锐度。

默认结构：

- 3-5 条 AI 热点。
- 每条包含标题、来源、一句话摘要和一句人工判断。
- 热点类型包括模型发布、AI 产品、开源项目、GitHub 趋势、公司动态、开发者生态和重要争议。
- 每条尽量说明它和论文选题、实验方法、复现或 AI 应用开发有什么关系。

#### 次文章 2，arXiv 高热度文章速报

次文章 2 用于快速覆盖当天高热论文，让读者知道哪些论文值得加入阅读列表。

默认结构：

- 3-5 篇 arXiv 高热度文章。
- 每篇包含论文名、arXiv 链接、方向标签、核心亮点、适合谁读。
- 标记是否值得后续展开成长论文解读。
- 优先选择与 AI 论文辅导业务相关的论文，包括 Agent、LLM、RAG、评测、多模态、AI coding、AI safety、训练/推理优化等方向。

### 7.3 Content Workflow

1. 定时抓取信源。
2. 清洗、去重、聚类。
3. 对新闻、论文、项目分别评分。
4. 生成候选选题。
5. 生成选题池、次文章 1 和次文章 2。
6. 主文章保持待选择状态，等待使用者读完素材后手动选择题目。
7. 使用者点击选题生成长文。
8. 生成 3 个模块的文章结构。
7. 调用 `khazix-writer` 改写成长文风格。
9. 调用 `image2` 为主文章生成封面图、机制图、流程图、金句图。
10. 输出公众号排版稿。
11. 使用者人工审核。
12. 复制到公众号后台发布。

### 7.4 Data Sources

| Source Type | Candidate Integration |
| --- | --- |
| AI 行业新闻 | `ai-news-radar`, RSSHub, 官方博客 RSS |
| 自媒体热点 | RSSHub, TopHub, Buzzing, Hacker News, X 公开信号 |
| 论文 | arXiv API, arXiv RSS, Semantic Scholar API |
| 代码与复现 | Papers with Code, GitHub Search, GitHub Trending |
| 工具/产品 | Product Hunt, GitHub releases, 官方 changelog |

### 7.5 Article Generation

文章生成不直接一稿到底，分为 4 步。

1. **选题判断**
   判断这个选题是否有趣、有信息量、有共鸣，是否适合论文辅导业务。

2. **结构生成**
   先生成文章主线、论点、素材来源、配图需求。

3. **风格改写**
   使用 `khazix-writer` 降 AI 味，写成更像一个有见识的普通人在认真聊一件事。

4. **四层自检**
   检查禁用词、报告腔、空泛论断、AI 味、事实风险和引用来源。

### 7.6 Image Generation

图片使用 `image2`，由使用者提供 API Key。

每篇主文章默认生成 3 类图。

| Image Type | Purpose |
| --- | --- |
| 封面图 | 提升打开率，表达当天主选题 |
| 机制图 | 解释论文方法、模型结构或工作流 |
| 金句图 | 适合朋友圈、社群、文章中段视觉停顿 |

图片风格应与前端一致，高级、鲜艳、动态、有科技感。避免廉价 AI 紫色渐变，避免纯装饰图。

### 7.7 Frontend Design Direction

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

### 7.8 Key Features

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

#### Feature 2, Topic Scoring

每个候选选题有 4 个评分。

| Score | Meaning |
| --- | --- |
| Heat | 当前热度 |
| Relevance | 与 AI 论文辅导业务相关度 |
| Writeability | 是否适合写成长文 |
| Conversion | 是否能自然引导咨询或服务 |

#### Feature 3, Paper Analyzer

输入论文链接或自动选中论文后，生成：

- 论文一句话总结。
- 研究问题。
- 方法拆解。
- 实验可信度。
- 局限性。
- 可复现代码。
- 可延伸论文选题。
- 公众号写作角度。

#### Feature 4, Article Workshop

生成稿件包：

```text
article.md
article-wechat.html
cover.png
figures/
sources.md
review-checklist.md
```

#### Feature 5, WeChat Layout Preview

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

#### Feature 6, Mature Markdown Editor Experience

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

### 7.9 Technology

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
| Writing | LLM + khazix-writer |
| Image | image2 |
| Layout | 内置 Markdown to WeChat HTML fallback + doocs/md style compatibility |
| Mature Editor | React 内嵌 Markdown 编辑器，参考 doocs/md 体验，后续可接宽松许可证渲染内核 |

### 7.10 Assumptions

- `image2` 可以稳定生成封面图和解释图。
- `khazix-writer` 的风格适合该公众号账号，后续可能需要微调成你自己的口吻。
- `ai-news-radar` 的源质量足够做行业热点初筛。
- 微信公众号最终由人工复制发布，因此无需处理自动群发合规问题。
- 论文解析需要事实核查，不能只依赖模型总结。

## 8. Release

### MVP, 2-4 weeks

Scope:

- 接入 `ai-news-radar`。
- 接入 arXiv API。
- 每日生成 5-10 个候选选题。
- 每日生成 1 套 3 模块文章包：主文章默认为待选择，使用者手动选择后生成长论文解读；次文章 1 AI 热点、次文章 2 arXiv 高热度文章速报自动生成。
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
- GitHub 项目监控。
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
| 热点质量低 | 加入业务相关度和可写性评分 |
| 信息源失效 | 每日源健康检查 |
| 公众号复制排版错乱 | 输出 Markdown 和 HTML 双版本 |
| 第三方排版工具许可证不兼容 | 优先选择 WTFPL/MIT/Apache 类宽松许可证；不复制 BUSL/商业授权工具源码 |
| 动效影响使用 | 审核页降低动效，支持 reduced motion |

## 10. Open Questions

| Question | Owner | Deadline |
| --- | --- | --- |
| image2 的具体 API 格式是什么 | Gary | 开发前 |
| 公众号最终排版偏短文还是长文 | Gary | MVP 前 |
| 是否需要形成你自己的写作风格，而不是完全使用 khazix 风格 | Gary | V1 前 |
| 是否需要保存客户咨询转化数据 | Gary | V1 前 |
| 主强调色选择电蓝、荧光绿还是珊瑚红 | Gary | 视觉设计前 |
