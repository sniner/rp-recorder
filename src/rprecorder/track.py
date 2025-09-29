from __future__ import annotations

import logging
import re

from dataclasses import dataclass
from typing import Tuple


log = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    filepos: int
    timepos: float
    name: str
    cover: str

    def timepos_str(self) -> str:
        secs = int(self.timepos)
        h = secs // 3600
        m = (secs - h * 3600) // 60
        s = secs % 60
        return f"{h}:{m:02d}:{s:02d}"

    def artist_title(self) -> Tuple[str, str]:
        artist, title = re.split(r"\s+-\s+", self.name, maxsplit=1)
        return artist, title
