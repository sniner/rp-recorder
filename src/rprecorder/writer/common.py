from __future__ import annotations

import pathlib

from abc import ABC, abstractmethod

from ..track import TrackInfo


class Writer(ABC):
    def __init__(self, path: str | pathlib.Path) -> None:
        self.path = pathlib.Path(path)

    @abstractmethod
    def add_track(self, track: TrackInfo) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    def remove(self) -> None:
        if self.path.exists():
            self.path.unlink()
