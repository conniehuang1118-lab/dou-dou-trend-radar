from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime

from app.core.types import RawSignal


class Provider(ABC):
    source_id: str
    name: str
    provider_type: str
    is_mock: bool

    @abstractmethod
    def fetch(self) -> list[RawSignal]:
        raise NotImplementedError

    def make_signal_id(self, title: str, url: str, publish_time: datetime) -> str:
        base = f"{self.source_id}|{title}|{url}|{publish_time.isoformat()}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:24]
