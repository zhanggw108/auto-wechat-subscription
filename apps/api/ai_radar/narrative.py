from __future__ import annotations

from typing import Dict, Iterable, List

from .models import NarrativeType


NARRATIVE_LABELS: dict[NarrativeType, str] = {
    "evaluation_review": "评测复盘型",
    "mechanism_explainer": "机制拆解型",
    "controversy_judgement": "争议判断型",
    "trend_slice": "趋势切片型",
    "application_translation": "应用转译型",
}

NARRATIVE_KEYWORDS: list[tuple[NarrativeType, tuple[str, ...], str]] = [
    (
        "controversy_judgement",
        ("versus", " vs ", "trade-off", "tradeoff", "comparison", "rag", "long-context", "long context"),
        "标题或摘要包含路线比较信号，适合写成争议双方的证据判断。",
    ),
    (
        "application_translation",
        ("agent", "coding", "robot", "tool use", "tool call", "workflow", "deployment", "workload", "serving"),
        "标题和摘要命中 agent、coding、robot、workflow 或 serving 信号，适合转译为产品和工程启发。",
    ),
    (
        "mechanism_explainer",
        ("framework", "architecture", "system", "training", "inference", "optimization", "distillation", "routing", "geometry", "defense"),
        "标题和摘要命中机制、系统或训练方法信号，适合拆解核心机制为什么成立。",
    ),
    (
        "evaluation_review",
        ("benchmark", "evaluation", "evaluating", "testbed", "leaderboard", "arena"),
        "标题和摘要命中评测、benchmark、testbed 或 leaderboard 信号，核心价值在于重新定义评测口径。",
    ),
]

NARRATIVE_STRATEGIES: dict[NarrativeType, str] = {
    "evaluation_review": "推荐写法：评测复盘型。围绕旧评测哪里失真、新评测测了什么、实验结果暴露什么失败模式、它对后续模型或产品有什么约束展开。",
    "mechanism_explainer": "推荐写法：机制拆解型。围绕核心机制、为什么可能有效、实验如何证明机制成立、方法边界在哪里展开。",
    "controversy_judgement": "推荐写法：争议判断型。围绕争议双方各自成立条件、论文证据支持哪一边、哪些结论不能外推、作者判断展开。",
    "trend_slice": "推荐写法：趋势切片型。围绕多个信号共同指向的变化、为什么现在值得关注、后续该追踪什么展开。",
    "application_translation": "推荐写法：应用转译型。围绕研究结论对产品、工程和工作流的启发、落地前缺什么证据展开。",
}

FORBIDDEN_MAIN_ARTICLE_TERMS = (
    "配图建议",
    "image2",
    "封面图",
    "机制图",
    "发布前复核清单",
    "发布前必须",
    "当前学术价值参考分",
    "内部评分",
    "后台",
)


def recommend_narrative(title: str, abstract: str, categories: Iterable[str], method_summary: str) -> Dict[str, object]:
    title_method = " ".join([title, method_summary]).lower()
    text = " ".join([title, abstract, " ".join(categories), method_summary]).lower()
    matches: list[tuple[NarrativeType, str]] = []
    if any(keyword in title_method for keyword in ("benchmark", "evaluation", "evaluating", "testbed", "leaderboard", "arena", "swe-bench")):
        matches.append(("evaluation_review", "标题和摘要命中评测、benchmark、testbed 或 leaderboard 信号，核心价值在于重新定义评测口径。"))
    if any(keyword in text for keyword in ("routing", "firewall", "geometry", "geometric", "defense")):
        matches.append(("mechanism_explainer", "标题和摘要命中路由、防御或几何机制信号，适合拆解核心机制为什么成立。"))
    if any(keyword in text for keyword in ("coding agent workload", "serving", "tool call", "workflow", "deployment")):
        matches.append(("application_translation", "标题和摘要命中编码智能体工作负载、工具调用或服务优化信号，适合转译为产品和工程启发。"))
    for narrative_type, keywords, reason in NARRATIVE_KEYWORDS:
        if narrative_type == "controversy_judgement":
            has_comparison = any(keyword in text for keyword in ("versus", " vs ", "trade-off", "tradeoff", "comparison"))
            has_rag_context = "rag" in text and ("long-context" in text or "long context" in text)
            if not has_comparison and not has_rag_context:
                continue
        elif not any(keyword in text for keyword in keywords):
            continue
        if any(existing_type == narrative_type for existing_type, _reason in matches):
            continue
        matches.append((narrative_type, reason))

    primary, reason = matches[0] if matches else ("trend_slice", "未命中更明确的评测、机制、争议或应用信号，默认写成趋势切片型。")
    alternatives: List[NarrativeType] = []
    for narrative_type, _reason in matches[1:]:
        if narrative_type != primary and narrative_type not in alternatives:
            alternatives.append(narrative_type)
        if len(alternatives) >= 2:
            break
    return {
        "type": primary,
        "label": NARRATIVE_LABELS[primary],
        "reason": reason,
        "alternatives": alternatives,
    }


def narrative_strategy(narrative_type: NarrativeType | None) -> str:
    return NARRATIVE_STRATEGIES[narrative_type or "trend_slice"]


def forbidden_main_article_reason(markdown: str) -> str:
    if "####" in markdown:
        return "contains unsupported heading level ####"
    for term in FORBIDDEN_MAIN_ARTICLE_TERMS:
        if term in markdown:
            return f"contains forbidden internal content: {term}"
    if markdown.count("\n### ") < 2 and not markdown.lstrip().startswith("### "):
        return "main article must contain at least two ### headings"
    return ""
