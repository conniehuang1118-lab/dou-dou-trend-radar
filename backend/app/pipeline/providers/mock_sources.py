from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

from app.core.types import RawSignal
from app.pipeline.providers.base import Provider


def _search_url(title: str) -> str:
    return f"https://www.baidu.com/s?wd={quote_plus(title)}"


class JikeMockProvider(Provider):
    source_id = "jike_mock"
    name = "即刻(MOCK)"
    provider_type = "mock"
    is_mock = True

    def fetch(self) -> list[RawSignal]:
        now = datetime.now(timezone.utc)
        topics = [
            ("开源AI助手集体爆发", "多个开源AI助手项目同日发布并引发大量讨论", 0, 8000),
            ("国产AI视频模型发布", "新一代文生视频模型登上多平台热榜", 10, 6200),
            ("设计系统自动化成为团队标配", "中大型产品团队开始升级自动化设计系统", 20, 5400),
            ("创业公司开始收缩广告预算", "增长团队转向精细化投放与复购经营", 45, 3300),
            ("新款AI眼镜进入量产", "智能硬件赛道出现新热度", 55, 4100),
        ]
        items: list[RawSignal] = []
        for idx, (title, content, mins, views) in enumerate(topics, start=1):
            publish = now - timedelta(minutes=mins)
            url = _search_url(title)
            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, publish),
                    source_id=self.source_id,
                    title=title,
                    content=content,
                    url=url,
                    author="jike_user",
                    publish_time=publish,
                    metrics={"likes": views / 20, "comments": views / 45, "reposts": views / 80, "views": float(views)},
                    extracted_keywords=["即刻", "热点"],
                    language="zh",
                )
            )
        return items


class BilibiliMockProvider(Provider):
    source_id = "bilibili_mock"
    name = "B站科技(MOCK)"
    provider_type = "mock"
    is_mock = True

    def fetch(self) -> list[RawSignal]:
        now = datetime.now(timezone.utc)
        videos = [
            ("开源AI助手集体爆发：实测对比", "视频创作者实测多个AI助手能力差异", 5, 120000),
            ("国产AI视频模型发布全解析", "模型效果与算力成本深度拆解", 15, 95000),
            ("设计系统自动化实践", "从组件到 token 的自动化搭建流程", 26, 76000),
            ("新款AI眼镜体验", "硬件上手和场景评测", 33, 84000),
            ("创业公司如何做增长", "创业团队增长复盘", 70, 52000),
        ]
        items: list[RawSignal] = []
        for idx, (title, content, mins, views) in enumerate(videos, start=1):
            publish = now - timedelta(minutes=mins)
            url = _search_url(title)
            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, publish),
                    source_id=self.source_id,
                    title=title,
                    content=content,
                    url=url,
                    author="up主",
                    publish_time=publish,
                    metrics={"likes": views / 25, "comments": views / 120, "reposts": views / 200, "views": float(views)},
                    extracted_keywords=["B站", "科技"],
                    language="zh",
                )
            )
        return items


class MockBurstProvider(Provider):
    source_id = "mock_burst"
    name = "种子爆发信号(MOCK)"
    provider_type = "mock"
    is_mock = True

    def fetch(self) -> list[RawSignal]:
        now = datetime.now(timezone.utc)
        burst_topics = [
            ("开源AI助手集体爆发", "多个平台同步讨论开源AI助手", 3, 15000),
            ("国产AI视频模型发布", "AI视频模型快速刷屏", 8, 13200),
            ("设计系统自动化成为团队标配", "设计自动化引发产品与设计团队讨论", 12, 9800),
        ]

        long_tail = [
            "AIGC广告素材自动化", "AI编程助手企业化落地", "低代码平台出海", "芯片新品量产", "机器人创业融资",
            "SaaS涨价策略", "数据治理工具升级", "开源数据库发布", "移动端设计趋势", "智能客服升级",
            "多模态检索方案", "内容创作者增长", "品牌营销新打法", "自动驾驶发布", "智能家居互联标准",
            "私域运营工具", "电商算法更新", "独立开发者盈利", "创业团队组织升级", "AI教育产品热度上升",
            "AR交互设计实践", "开源模型压缩", "端侧推理加速", "企业知识库建设", "社交产品改版",
        ]

        items: list[RawSignal] = []
        for idx, (title, content, mins, views) in enumerate(burst_topics, start=1):
            publish = now - timedelta(minutes=mins)
            url = _search_url(title)
            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, publish),
                    source_id=self.source_id,
                    title=title,
                    content=content,
                    url=url,
                    author="seed",
                    publish_time=publish,
                    metrics={"likes": views / 18, "comments": views / 35, "reposts": views / 60, "views": float(views)},
                    extracted_keywords=["爆发", "趋势", "全网"],
                    language="zh",
                )
            )

        for idx, title in enumerate(long_tail, start=100):
            mins = 20 + (idx % 120)
            views = 1200 + (idx % 9) * 380
            publish = now - timedelta(minutes=mins)
            url = _search_url(title)
            content = f"{title} 相关讨论持续上升，多个平台出现信号。"
            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, publish),
                    source_id=self.source_id,
                    title=title,
                    content=content,
                    url=url,
                    author="seed",
                    publish_time=publish,
                    metrics={"likes": views / 22, "comments": views / 55, "reposts": views / 90, "views": float(views)},
                    extracted_keywords=["趋势", "信号"],
                    language="zh",
                )
            )

        return items
