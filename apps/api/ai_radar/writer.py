from __future__ import annotations


REPORT_TONE_REPLACEMENTS = {
    "本文首先": "这件事先别急着下结论，我们先看",
    "首先": "先看",
    "其次": "再看",
    "最后": "收回来讲",
    "综上所述": "我的判断",
}


def rewrite_khazix_style(markdown: str) -> str:
    rewritten = markdown
    for old, new in REPORT_TONE_REPLACEMENTS.items():
        rewritten = rewritten.replace(old, new)
    if "我的判断" not in rewritten:
        rewritten += "\n\n## 我的判断\n\n这件事值得写，不是因为它听起来新，而是因为它能落到选题、实验和复现这三个真实问题上。\n"
    if "不是因为" not in rewritten:
        rewritten += "\n\n它不是因为概念热才重要，而是因为它能帮学生把研究问题拆得更具体。\n"
    return rewritten
