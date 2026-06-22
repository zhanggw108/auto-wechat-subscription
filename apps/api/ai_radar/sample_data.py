from __future__ import annotations

from typing import List

from .models import Paper, Signal, Source


def seed_sources(date: str) -> List[Source]:
    created_at = f"{date}T07:30:00Z"
    return [
        Source(
            id="source-arxiv-cs-ai",
            name="arXiv cs.AI / cs.LG",
            type="arxiv",
            url="https://export.arxiv.org/api/query?search_query=cat:cs.AI",
            last_success_at=created_at,
            created_at=created_at,
        ),
        Source(
            id="source-ai-news-radar",
            name="AI News Radar",
            type="rss",
            url="https://example.com/ai-news-radar.xml",
            last_success_at=created_at,
            created_at=created_at,
        ),
        Source(
            id="source-github-trending",
            name="GitHub AI Trending",
            type="github",
            url="https://github.com/trending/python?since=daily",
            last_success_at=created_at,
            created_at=created_at,
        ),
        Source(
            id="source-official-blogs",
            name="Official AI Blogs",
            type="rss",
            url="https://openai.com/news/rss.xml",
            last_success_at=created_at,
            created_at=created_at,
        ),
    ]


def seed_papers(date: str) -> List[Paper]:
    return [
        Paper(
            id="paper-agent-lab",
            arxiv_id="2501.04227",
            title="Agent Laboratory: Using LLM Agents as Research Assistants",
            authors=[
                "Samuel Schmidgall",
                "Yusheng Su",
                "Ze Wang",
                "Ximeng Sun",
                "Jialian Wu",
                "Xiaodong Yu",
                "Jiang Liu",
                "Zicheng Liu",
                "Emad Barsoum",
            ],
            abstract=(
                "Agent Laboratory 是一个基于 LLM agent 的自动化科研框架。它从人类给出的研究想法出发，"
                "依次推进文献综述、实验和报告写作，同时允许人类在每个阶段提供反馈。"
            ),
            pdf_url="https://arxiv.org/pdf/2501.04227",
            code_url="https://github.com/SamuelSchmidgall/AgentLaboratory",
            published_at="2025-01-08T01:58:42Z",
            categories=["cs.AI", "cs.LG"],
            method_summary=(
                "Agent Laboratory 把科研流程拆成文献综述、实验和报告写作三个阶段，让不同角色的 agent 围绕同一个研究想法协作，"
                "并在每个阶段保留人类反馈入口。"
            ),
            experiment_summary=(
                "论文报告里，o1-preview 在测试的后端模型中效果最好；加入人类反馈后，产出质量会进一步提升；"
                "作者还给出一个很抓眼球的数字，和此前自主科研方法相比，成本降低了 84%。"
            ),
            limitations=(
                "The results still depend on human evaluation and selected tasks. The paper is better read as a workflow prototype, "
                "not proof that agents can independently produce reliable research."
            ),
            replication_value=88,
            extension_topics=[
                "面向毕业论文的 agent 实验设计助手",
                "研究型 agent 的证据约束与幻觉评测",
                "多 agent 协作在 baseline 选择中的可靠性",
            ],
        ),
        Paper(
            id="paper-long-context-rag",
            arxiv_id="2407.16833",
            title="Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach",
            authors=["Zhuowan Li", "Cheng Li", "Mingyang Zhang", "Qiaozhu Mei", "Michael Bendersky"],
            abstract=(
                "这篇论文系统比较了检索增强生成和长上下文 LLM，并提出 Self-Route，"
                "用模型自我判断在 RAG 和长上下文路径之间做选择，以降低成本并尽量保持效果。"
            ),
            pdf_url="https://arxiv.org/pdf/2407.16833",
            code_url=None,
            published_at="2024-07-23T20:51:52Z",
            categories=["cs.CL", "cs.IR"],
            method_summary="论文在多个公开数据集上比较 RAG 和长上下文 LLM，再用模型自我反思来决定每个问题走检索路径还是长上下文路径。",
            experiment_summary="论文报告说，在资源充足时，长上下文模型经常更强；但 RAG 的成本优势和路由效率仍然让它很难被简单淘汰。",
            limitations="The conclusions depend on the tested datasets and models; students should re-run newer model baselines before treating it as settled.",
            replication_value=82,
            extension_topics=["长上下文模型中的检索必要性", "RAG 引用可信度评测", "课程论文中的消融实验设计"],
        ),
    ]


def seed_signals(date: str) -> List[Signal]:
    published = f"{date}T06:00:00Z"
    return [
        Signal(
            id="signal-agent-lab-paper",
            source_id="source-arxiv-cs-ai",
            kind="paper",
            title="Agent Laboratory shows how research agents can structure literature review and experiments",
            summary="Agent Laboratory 把科研助理拆成文献综述、实验和报告写作几个阶段，适合拿来讨论研究型 agent 到底能帮学生做什么。",
            url="https://arxiv.org/abs/2501.04227",
            published_at="2025-01-08T01:58:42Z",
            tags=["agents", "research-workflow", "paper"],
            heat=94,
            entities={"papers": ["Agent Laboratory"], "methods": ["multi-agent"]},
        ),
        Signal(
            id="signal-agent-lab-code",
            source_id="source-github-trending",
            kind="repo",
            title="Agent Laboratory repository exposes the research workflow implementation",
            summary="配套仓库展示了从文献综述到实验、再到报告写作的端到端流程，适合用来观察研究型 agent 的工程边界。",
            url="https://github.com/SamuelSchmidgall/AgentLaboratory",
            published_at=published,
            tags=["github", "agents", "reproducibility"],
            heat=85,
            entities={"repos": ["agent-laboratory"]},
        ),
        Signal(
            id="signal-long-context-rag",
            source_id="source-arxiv-cs-ai",
            kind="paper",
            title="Long-context RAG paper questions the end of retrieval",
            summary="这篇论文比较 RAG 和长上下文 LLM，核心启发是不要急着二选一，路由机制可能在质量和成本之间给出更现实的折中。",
            url="https://arxiv.org/abs/2407.16833",
            published_at="2024-07-23T20:51:52Z",
            tags=["rag", "long-context", "paper"],
            heat=88,
            entities={"papers": ["RAG Under Long Context"]},
        ),
        Signal(
            id="signal-openai-evals",
            source_id="source-official-blogs",
            kind="news",
            title="Anthropic discusses how to evaluate AI agents",
            summary="Anthropic 的 agent eval 文章强调，评测要覆盖任务结果、轨迹、grader 可靠性和必要的人类复核，不能只看单轮答案。",
            url="https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents",
            published_at="2026-01-22T00:00:00Z",
            tags=["evals", "agents", "official"],
            heat=80,
            entities={"companies": ["Anthropic"]},
        ),
        Signal(
            id="signal-anthropic-context",
            source_id="source-ai-news-radar",
            kind="news",
            title="Anthropic highlights context engineering patterns",
            summary="Anthropic 强调有效 agent 往往先从简单、可组合的 workflow 开始，再逐步走向更自主的系统。",
            url="https://www.anthropic.com/engineering/building-effective-agents",
            published_at="2024-12-19T00:00:00Z",
            tags=["context-engineering", "agents"],
            heat=78,
            entities={"companies": ["Anthropic"]},
        ),
        Signal(
            id="signal-github-evalkit",
            source_id="source-github-trending",
            kind="repo",
            title="OpenAI Evals remains a useful baseline for model evaluation workflows",
            summary="OpenAI Evals 仓库给了学生一个具体入口，可以从数据集、grader 和回归式模型检查开始搭评测 baseline。",
            url="https://github.com/openai/evals",
            published_at=published,
            tags=["github", "evals", "tooling"],
            heat=76,
            entities={"repos": ["openai/evals"]},
        ),
        Signal(
            id="signal-product-agent-builder",
            source_id="source-ai-news-radar",
            kind="product",
            title="LangGraph gives agent workflows a concrete engineering baseline",
            summary="LangGraph 关注持久执行、状态管理和可控 agent workflow，适合作为可复现 agent 工程的参考基线。",
            url="https://github.com/langchain-ai/langgraph",
            published_at=published,
            tags=["product", "agents", "debugging"],
            heat=72,
            entities={"products": ["LangGraph"]},
        ),
        Signal(
            id="signal-post-paper-topics",
            source_id="source-ai-news-radar",
            kind="paper",
            title="AgentBench keeps agent evaluation grounded in interactive tasks",
            summary="AgentBench 把 LLM agent 放进多个交互环境里评测，也记录了长期推理和指令遵循等常见失败点。",
            url="https://arxiv.org/abs/2308.03688",
            published_at="2023-08-07T16:08:11Z",
            tags=["thesis", "evals", "agents"],
            heat=74,
            entities={"topics": ["agent evaluation"]},
        ),
    ]
