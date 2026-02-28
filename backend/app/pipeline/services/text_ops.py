from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import jieba.analyse


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def strong_fingerprint(title: str, url: str) -> str:
    base = f"{normalize_text(title)}::{normalize_url(url)}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def weak_fingerprint(title: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalize_text(title))
    return hashlib.sha1(slug.encode("utf-8")).hexdigest()


def normalize_url(url: str) -> str:
    u = (url or "").strip().lower()
    u = u.replace("https://", "").replace("http://", "")
    return u.rstrip("/")


def extract_keywords(text: str, top_k: int = 8) -> list[str]:
    if not text:
        return []
    kws = [x.strip() for x in jieba.analyse.extract_tags(text, topK=top_k) if x.strip()]
    if kws:
        return kws
    fallback = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text.lower())
    return fallback[:top_k]


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


def categorize_by_keywords(keywords: list[str], title: str, content: str) -> str:
    bag = " ".join([title, content, *keywords]).lower()

    if any(k in bag for k in ["ai", "大模型", "人工智能", "智能体", "llm", "agent", "模型"]):
        return "AI"
    if any(k in bag for k in ["科技", "芯片", "手机", "硬件", "发布会", "tech"]):
        return "科技"
    if any(k in bag for k in ["创业", "融资", "公司", "创投", "vc", "startup"]):
        return "创业"
    if any(k in bag for k in ["设计", "ui", "ux", "figma", "品牌", "视觉"]):
        return "设计"
    return "其它"


def summarize(texts: list[str], max_len: int = 120) -> str:
    merged = "；".join([t.strip() for t in texts if t and t.strip()])
    merged = re.sub(r"\s+", " ", merged)
    if len(merged) <= max_len:
        return merged
    return merged[: max_len - 1] + "…"


def counter_top(items: list[str], limit: int) -> list[str]:
    return [k for k, _ in Counter([x for x in items if x]).most_common(limit)]


def safe_log(x: float) -> float:
    return math.log(1 + max(0.0, x))
