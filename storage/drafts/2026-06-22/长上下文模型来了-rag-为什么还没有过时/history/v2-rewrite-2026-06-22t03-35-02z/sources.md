# 来源清单

1. Long-context RAG paper questions the end of retrieval
   URL: https://arxiv.org/abs/2407.16833
   Used for: 这篇论文比较 RAG 和长上下文 LLM，核心启发是不要急着二选一，路由机制可能在质量和成本之间给出更现实的折中。
   Confidence: high
   Risk: 无特殊风险，发布前仍建议人工复核。

2. Anthropic discusses how to evaluate AI agents
   URL: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
   Used for: Anthropic 的 agent eval 文章强调，评测要覆盖任务结果、轨迹、grader 可靠性和必要的人类复核，不能只看单轮答案。
   Confidence: high
   Risk: 无特殊风险，发布前仍建议人工复核。

3. Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach
   URL: https://arxiv.org/pdf/2407.16833
   Used for: 论文在多个公开数据集上比较 RAG 和长上下文 LLM，再用模型自我反思来决定每个问题走检索路径还是长上下文路径。
   Confidence: high
   Risk: 实验结论需要人工阅读 PDF 后确认细节和指标。
