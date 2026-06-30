# 每日论文选题量化评分系统设计

## 背景

当前 `long_articles` 的最终 5 条候选由 LLM 在候选上下文中自行选择。后端会校验数量、论文来源和格式，但不会用可审计的规则决定“哪 5 篇必须入选”。这导致每天的长文候选难以解释：只能从 LLM 生成的摘要和角度推断原因，无法回答某篇论文为什么入选、另一篇为什么被排除。

本次设计目标是把每日长文候选从“LLM 自由选择”改成“代码量化评分排序”。LLM 只负责把已选定的 5 篇论文改写成适合公众号工作台展示的标题、摘要和角度，不再拥有替换论文的权力。

## 目标

- 每天选出的 5 条长文候选必须来自可量化评分。
- 国际知名大厂、研究机构、高影响力学者或工程人物发出的论文和文章获得高权重。
- 每条入选候选都能展示总分、分项分数和入选原因。
- 可查看当天所有被评分论文，解释“为什么某篇没入选”。
- 第一版不接外部 citation、Semantic Scholar、X 实时传播量等不稳定依赖。

## 不做的事

- 不改变 `ai_hotspots` 和 `arxiv_papers` 的生成逻辑。
- 不让 LLM 决定最终 5 条长文候选。
- 不接 Semantic Scholar、Google Scholar、X、Reddit 等外部指标 API。
- 不做复杂前端筛选面板。
- 不做语义去重，只对明确的 arXiv ID、URL、dedupe key 做历史惩罚。

## 总体方案

采用规则打分器直接选择前 5 条。

新增一个轻量评分模块，建议命名为 `apps/api/ai_radar/scoring.py`。该模块接收当天的 `papers`、`signals`、历史 topic pack 和影响力配置，对每篇论文生成 `PaperScore`。后端按 `total_score` 降序选出前 5 篇作为 `long_articles` 的锁定来源。

刷新 `topic_pack` 时，数据流变为：

1. 抓取信源，生成当天 `papers` 和 `signals`。
2. 对全部可用论文运行量化评分。
3. 按分数和 tie-breaker 选出前 5 篇论文。
4. 将这 5 篇论文作为锁定 `long_articles` 输入传给 LLM。
5. LLM 只能生成这 5 篇的 `title`、`summary`、`angle`，不能替换论文。
6. 后端用锁定论文的 `arxiv_id` 和 `source_urls` 覆盖 LLM 返回值，防止模型换论文。
7. 保存 `TopicPackItem.score_detail` 和完整评分文件。

## 评分公式

每篇论文总分 100 分。

```text
total_score =
  research_relevance
  + method_substance
  + experiment_strength
  + influence_score
  + freshness_and_heat
  + writeability
  - penalties
```

### research_relevance，25 分

衡量论文是否适合 AI 研究公众号主线。根据标题、摘要、分类、标签命中关键词加分。

关键词包括但不限于：

- LLM
- multimodal
- agent
- reasoning
- training
- inference
- safety
- coding
- robotics
- evaluation
- benchmark
- AI4Science
- diffusion
- alignment
- interpretability

目标是过滤虽然在 arXiv cs 里、但不适合长文主线的论文。

### method_substance，20 分

衡量是否有明确方法、系统、理论或数据贡献。根据摘要中的方法信号加分。

方法信号包括：

- framework
- architecture
- training
- distillation
- optimization
- regularization
- benchmark
- dataset
- theory
- simulation
- evaluation
- pipeline
- system

目标是优先选择能讲清“方法贡献”的论文，而不是只有概念包装的文章。

### experiment_strength，15 分

衡量实验验证强度。根据摘要中是否出现评测、对照、消融、真实场景、大规模实验等信号加分。

实验信号包括：

- evaluation
- benchmark
- ablation
- comparison
- human study
- real-world
- large-scale
- SOTA
- empirical
- user study

目标是避免缺少验证的论文进入长文主线。

### influence_score，25 分

强加分项，但不超过 25 分。高影响力来源可以显著提高排序，但不能完全压倒论文质量。

来源包括三类：

1. 知名机构：
   - OpenAI
   - Anthropic
   - Google DeepMind
   - Google Research
   - Meta AI
   - Microsoft Research
   - NVIDIA
   - Apple
   - xAI
   - DeepSeek
   - Qwen
   - Alibaba
   - ByteDance
   - Tencent AI Lab
   - Tsinghua University
   - Stanford
   - MIT
   - UC Berkeley
   - CMU
2. 高影响力人物：
   - Yann LeCun
   - Geoffrey Hinton
   - Yoshua Bengio
   - Ilya Sutskever
   - Andrej Karpathy
   - François Chollet
   - Demis Hassabis
   - Fei-Fei Li
   - Pieter Abbeel
   - Andrew Ng
3. 高影响力信源域名：
   - openai.com
   - anthropic.com
   - deepmind.google
   - ai.meta.com
   - blogs.nvidia.com
   - microsoft.com
   - apple.com
   - deepseek.com
   - qwenlm.github.io

第一版通过论文作者、摘要、标题、关联信号标题、信号摘要、信号 URL 域名匹配这些名单。未命中不扣分，只是 `influence_score=0`。

### freshness_and_heat，10 分

衡量新鲜度和热度。

加分来源：

- 近 24 小时发布或抓取。
- 多个信号指向同一论文。
- RSS、官方博客、GitHub、社交源出现相关讨论。
- arXiv 新论文和 RSS 热点互相印证。

### writeability，5 分

衡量是否容易写成公众号长文。

判断依据：

- 标题和摘要能拆出明确问题。
- 方法路径可解释。
- 实验或应用场景可讲。
- 有局限或争议可分析。
- 能形成“问题、方法、实验、局限、判断”的文章结构。

## 扣分规则

### history_penalty

如果最近 topic pack 历史中出现过相同 `arxiv_id`、URL 或 dedupe key，最多扣 30 分。

历史惩罚只做精确匹配，不做语义去重。原因是选题角度可以重复，但论文不能重复。

### weak_source_penalty

缺少 arXiv ID、PDF URL 或可信论文 URL 的条目不能进入长文候选。此类条目可进入热点，但不能进入 `long_articles`。

### low_ai_relevance_penalty

AI 相关性太弱时最多扣 20 分。若研究相关性低于硬阈值，可以直接排除。

## 排序规则

最终排序：

1. `total_score` 降序。
2. 同分时 `influence_score` 高者优先。
3. 再同分时 `experiment_strength` 高者优先。
4. 再同分时发布时间或抓取时间更新者优先。
5. 再同分按标题字母序，确保结果稳定。

最终前 5 篇作为 `long_articles` 锁定候选。

## 数据结构

### PaperScore

新增内部对象，用于计算和调试。

```text
paper_id
arxiv_id
title
total_score
score_detail:
  research_relevance:
    value
    reason
  method_substance:
    value
    reason
  experiment_strength:
    value
    reason
  influence_score:
    value
    reason
  freshness_and_heat:
    value
    reason
  writeability:
    value
    reason
  penalties:
    value
    reason
selection_reasons[]
matched_institutions[]
matched_people[]
matched_source_domains[]
matched_signals[]
```

### TopicPackItem.score_detail

给 `TopicPackItem` 增加 `score_detail` 字段，用于保存入选长文候选的评分明细。第一版只要求 `long_articles` 一定有评分；`ai_hotspots` 和 `arxiv_papers` 可以为空。

建议结构：

```json
{
  "total_score": 87,
  "research_relevance": {"value": 22, "reason": "标题和摘要命中 agent、evaluation、benchmark"},
  "method_substance": {"value": 18, "reason": "摘要包含 framework 和 benchmark"},
  "experiment_strength": {"value": 12, "reason": "包含大规模评测和对照实验"},
  "influence_score": {"value": 25, "reason": "命中 Google DeepMind"},
  "freshness_and_heat": {"value": 7, "reason": "近 24 小时 arXiv 新论文，且 RSS 出现相关讨论"},
  "writeability": {"value": 4, "reason": "可拆成问题、方法、实验、局限"},
  "penalties": {"value": 1, "reason": "无历史重复，仅有轻微来源缺失"},
  "selection_reasons": ["总分进入前 5", "命中高影响力机构", "实验信号明确"]
}
```

### 影响力配置

新增配置文件：

```text
apps/api/ai_radar/influence_sources.json
```

结构：

```json
{
  "institutions": [
    {"name": "OpenAI", "aliases": ["openai"], "weight": 25},
    {"name": "Google DeepMind", "aliases": ["deepmind", "google deepmind"], "weight": 25}
  ],
  "people": [
    {"name": "Yann LeCun", "aliases": ["yann lecun"], "weight": 20}
  ],
  "source_domains": [
    {"domain": "openai.com", "weight": 18},
    {"domain": "anthropic.com", "weight": 18}
  ]
}
```

配置损坏时刷新失败，并显示具体文件路径和 JSON 错误。不静默忽略。

## LLM 改写约束

`long_articles` 的论文选择由评分系统锁定。LLM 只负责为这 5 篇生成展示文本。

LLM 输入应包含：

- 锁定的 5 篇论文。
- 每篇论文的分项得分。
- 每篇论文的入选原因。
- 明确指令：不能替换论文，不能新增第 6 篇，不能改变 arXiv ID。

LLM 返回后，后端必须：

- 用锁定论文的 `arxiv_id`、`source_urls` 覆盖模型返回。
- 如果 LLM 返回数量不是 5，刷新失败。
- 如果 LLM 返回标题、摘要、角度缺失，可用论文标题和评分原因生成最小可用文案。
- 不接受 LLM 替换论文。

## 前端展示

第一版只做轻量展示，不做筛选面板。

长文候选卡片增加评分行：

```text
总分 87 | 影响力 25 | 方法 18 | 实验 12
入选原因：命中 Google DeepMind；摘要包含 benchmark / ablation；近 24 小时多信源出现。
```

如果某条没有 `score_detail`，前端不报错，只隐藏评分行。这兼容旧 topic pack。

## 调试文件

每次生成 topic pack 时保存完整评分文件：

```text
storage/topic-packs/YYYY-MM-DD/vNN/long-article-scores.json
```

内容包含当天所有被评分论文，不只前 5。字段包括：

- 论文基本信息
- 总分
- 分项分数
- 命中的机构、人物、域名、信号
- 扣分原因
- 是否入选
- 排名

该文件用于回答“为什么这篇没入选”。

## 错误处理

- 可评分论文少于 5 篇：刷新失败，错误为 `可评分论文不足 5 篇`。
- 影响力配置 JSON 损坏：刷新失败，错误包含配置文件路径。
- LLM 替换论文：后端覆盖为锁定论文；如果无法对齐，刷新失败。
- LLM 返回少于 5 条长文文案：刷新失败。
- 某篇论文没有影响力命中：不扣分，`influence_score=0`。
- 历史重复：扣分或排出前 5，不回退到 LLM 自选。

## 测试计划

### 单元测试

- 高影响力机构命中会提高 `influence_score`。
- 高影响力人物命中会提高 `influence_score`。
- 高影响力域名命中会提高 `influence_score`。
- 无影响力但方法和实验强的论文仍可获得高分。
- 历史中出现过相同 arXiv ID 时触发扣分。
- 缺少论文来源的条目不能进入长文候选。
- 影响力配置 JSON 损坏时报明确错误。

### 集成测试

- `/api/topic-packs/refresh` 返回的 `long_articles` 固定 5 条。
- 5 条按 `total_score` 排序。
- 每条 `long_articles` 都包含 `score_detail`。
- LLM 试图替换论文时，后端仍保留锁定论文。
- 生成 `storage/topic-packs/YYYY-MM-DD/vNN/long-article-scores.json`。

### 回归测试

- 旧 topic pack 没有 `score_detail` 时前端仍能展示。
- `ai_hotspots` 和 `arxiv_papers` 原有生成逻辑不变。
- LLM provider 未配置时仍按现有错误路径失败，不生成假数据。

## 实施顺序

1. 新增影响力配置 JSON。
2. 新增 `scoring.py` 和 `PaperScore`。
3. 在 topic pack 生成前计算并锁定前 5 篇论文。
4. 修改 LLM 输入，让模型只生成文案。
5. 修改后端合并逻辑，强制保留锁定论文来源。
6. 给 `TopicPackItem` 增加 `score_detail`。
7. 保存完整 `long-article-scores.json`。
8. 前端展示评分摘要。
9. 补齐测试。

## 开放问题

- 高影响力名单第一版需要人工维护，后续可以增加管理端编辑能力。
- 影响力分值可能需要观察 1-2 周后调参。
- 如果每天热门论文都来自同一机构，是否需要增加“多样性惩罚”暂不在第一版实现。
