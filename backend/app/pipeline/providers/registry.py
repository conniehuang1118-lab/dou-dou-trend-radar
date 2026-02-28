from __future__ import annotations

from app.pipeline.providers.base import Provider
from app.pipeline.providers.hotlist_sources import WeiboHotProvider, XTrendingProvider, ZhihuHotProvider
from app.pipeline.providers.mock_sources import BilibiliMockProvider, JikeMockProvider, MockBurstProvider
from app.pipeline.providers.rss_sources import RSSProvider
from app.pipeline.providers.tech_sources import GitHubTrendingProvider, HuggingFaceTrendingProvider


def build_provider_map() -> dict[str, Provider]:
    return {
        "kr36": RSSProvider("kr36", "36氪", "https://36kr.com/feed", ["36氪"]),
        "huxiu": RSSProvider("huxiu", "虎嗅", "https://www.huxiu.com/rss/0.xml", ["虎嗅"]),
        "sspai": RSSProvider("sspai", "少数派", "https://sspai.com/feed", ["少数派"]),
        "zhihu_hot": ZhihuHotProvider(),
        "weibo_hot": WeiboHotProvider(),
        "jike_mock": JikeMockProvider(),
        "github_trending": GitHubTrendingProvider(),
        "huggingface_trending": HuggingFaceTrendingProvider(),
        "bilibili_mock": BilibiliMockProvider(),
        "x_trending": XTrendingProvider(),
        "mock_burst": MockBurstProvider(),
    }
