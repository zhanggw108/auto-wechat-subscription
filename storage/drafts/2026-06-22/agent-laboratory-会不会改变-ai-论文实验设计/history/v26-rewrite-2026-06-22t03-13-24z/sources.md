# 来源清单

1. Agent Laboratory: Using LLM Agents as Research Assistants
   URL: https://arxiv.org/abs/2501.04227
   Used for: Agent Laboratory 是一个基于 LLM agent 的科研辅助框架，覆盖文献综述、实验和报告写作，并保留人类反馈入口。
   Confidence: high
   Risk: 不是 2026 年今日新论文，正文必须明确发布日期。

2. Agent Laboratory GitHub repository
   URL: https://github.com/SamuelSchmidgall/AgentLaboratory
   Used for: 配套仓库展示 Agent Laboratory 的实现入口，可用于复现和工程边界判断。
   Confidence: high
   Risk: 仓库可运行性仍需发布前按本机环境单独验证。

3. Demystifying evals for AI agents
   URL: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
   Used for: Agent 评测需要关注任务结果、执行轨迹、grader 可靠性和必要的人类复核。
   Confidence: high
   Risk: 作为评测方法论参考，不作为 Agent Laboratory 论文实验结果。

4. Building effective agents
   URL: https://www.anthropic.com/engineering/building-effective-agents
   Used for: 有效 agent 通常应从简单、可组合的 workflow 开始，再逐步走向更自主的系统。
   Confidence: high
   Risk: 作为工程方法论参考。

5. OpenAI Evals
   URL: https://github.com/openai/evals
   Used for: OpenAI Evals 可作为学生搭建数据集、grader 和回归式模型检查的 baseline 入口。
   Confidence: high
   Risk: 开源仓库状态会变化，发布前可再次打开确认。

6. LangGraph
   URL: https://github.com/langchain-ai/langgraph
   Used for: LangGraph 提供状态、持久执行和可控 agent workflow 的工程参考。
   Confidence: high
   Risk: 开源仓库状态会变化，发布前可再次打开确认。

7. Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach
   URL: https://arxiv.org/abs/2407.16833
   Used for: 论文比较 RAG 与长上下文 LLM，并讨论以路由方式平衡效果和成本。
   Confidence: high
   Risk: 不是今日新论文。

8. AgentBench: Evaluating LLMs as Agents
   URL: https://arxiv.org/abs/2308.03688
   Used for: AgentBench 在交互环境中评测 LLM agent，暴露长程推理、指令遵循和失败恢复等问题。
   Confidence: high
   Risk: 不是今日新论文。
