from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import List, Mapping, Tuple

from .models import Paper, Signal


ATOM = "{http://www.w3.org/2005/Atom}"


def parse_arxiv_feed(xml_text: str, source_id: str) -> Tuple[List[Paper], List[Signal]]:
    root = ET.fromstring(xml_text)
    papers: List[Paper] = []
    signals: List[Signal] = []
    for entry in root.findall(f"{ATOM}entry"):
        arxiv_url = _text(entry, f"{ATOM}id")
        title = _squash(_text(entry, f"{ATOM}title"))
        summary = _squash(_text(entry, f"{ATOM}summary"))
        published_at = _text(entry, f"{ATOM}published") or _text(entry, f"{ATOM}updated")
        arxiv_id = _arxiv_id(arxiv_url)
        authors = [_squash(_text(author, f"{ATOM}name")) for author in entry.findall(f"{ATOM}author")]
        categories = [category.attrib.get("term", "") for category in entry.findall(f"{ATOM}category")]
        pdf_url = next((link.attrib.get("href", "") for link in entry.findall(f"{ATOM}link") if link.attrib.get("title") == "pdf"), "")
        paper = Paper(
            id=f"paper-{_stable_id(arxiv_id)}",
            arxiv_id=arxiv_id,
            title=title,
            authors=[author for author in authors if author],
            abstract=summary,
            pdf_url=pdf_url or arxiv_url.replace("/abs/", "/pdf/"),
            code_url=None,
            published_at=published_at,
            categories=[item for item in categories if item],
            method_summary="待 LLM/人工解析：MVP connector 已保留论文摘要和 PDF 链接。",
            experiment_summary="待 LLM/人工解析：需要阅读论文实验章节后补充。",
            limitations="待 LLM/人工解析：发布前必须人工确认局限性。",
            replication_value=70,
            extension_topics=["基于该论文摘要提炼核心研究问题", "围绕方法贡献和实验可信度设计深度解读角度"],
        )
        signal = Signal(
            id=f"signal-{_stable_id(arxiv_id)}",
            source_id=source_id,
            kind="paper",
            title=title,
            summary=summary,
            url=arxiv_url,
            published_at=published_at,
            tags=["paper", *paper.categories],
            heat=72,
            entities={"papers": [title]},
        )
        papers.append(paper)
        signals.append(signal)
    return papers, signals


def parse_rss_feed(xml_text: str, source_id: str) -> List[Signal]:
    root = ET.fromstring(xml_text)
    signals: List[Signal] = []
    for item in root.findall("./channel/item")[:50]:
        guid = _squash(_text(item, "guid")) or _squash(_text(item, "link")) or _squash(_text(item, "title"))
        title = _squash(_text(item, "title"))
        summary = _squash(_text(item, "description"))
        published = _rss_date(_text(item, "pubDate"))
        signals.append(
            Signal(
                id=f"signal-{_stable_id(guid)}",
                source_id=source_id,
                kind="news",
                title=title,
                summary=summary,
                url=_squash(_text(item, "link")),
                published_at=published,
                tags=["news", "ai"],
                heat=68,
                entities={},
            )
        )
    return signals


def parse_github_search_repositories(payload: Mapping[str, object], source_id: str) -> List[Signal]:
    signals: List[Signal] = []
    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        return signals
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        repo_id = str(raw.get("id") or raw.get("full_name") or raw.get("html_url") or "")
        full_name = _squash(str(raw.get("full_name") or ""))
        html_url = _squash(str(raw.get("html_url") or ""))
        if not full_name or not html_url:
            continue
        description = _squash(str(raw.get("description") or ""))
        stars = _safe_int(raw.get("stargazers_count"))
        forks = _safe_int(raw.get("forks_count"))
        issues = _safe_int(raw.get("open_issues_count"))
        updated_at = _squash(str(raw.get("updated_at") or "1970-01-01T00:00:00Z"))
        topics = raw.get("topics") or []
        topic_tags = [str(topic) for topic in topics if str(topic).strip()] if isinstance(topics, list) else []
        heat = min(100, 55 + stars // 500 + forks // 100 + min(10, issues // 100))
        signals.append(
            Signal(
                id=f"signal-github-repo-{_stable_id(repo_id)}",
                source_id=source_id,
                kind="repo",
                title=full_name,
                summary=description or f"{full_name} GitHub repository",
                url=html_url,
                published_at=updated_at,
                tags=["github", *topic_tags],
                heat=heat,
                entities={"repos": [full_name]},
            )
        )
    return signals


def _text(node: ET.Element, path: str) -> str:
    found = node.find(path)
    return found.text if found is not None and found.text else ""


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _arxiv_id(url: str) -> str:
    value = url.rstrip("/").split("/")[-1]
    return re.sub(r"v\d+$", "", value)


def _stable_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    if cleaned:
        return cleaned[:64]
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _rss_date(value: str) -> str:
    if not value:
        return "1970-01-01T00:00:00Z"
    return parsedate_to_datetime(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
