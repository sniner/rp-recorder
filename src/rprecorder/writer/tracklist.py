from __future__ import annotations

import logging
import pathlib

from .common import TrackInfo, Writer


log = logging.getLogger(__name__)


class TrackListWriter(Writer):
    def __init__(
        self,
        path: str | pathlib.Path,
    ):
        super().__init__(path=path)
        self._write_failed: int = 0

    def add_track(self, track: TrackInfo) -> None:
        try:
            with open(self.path, "a") as f:
                print(f"{track.timepos_str()} -- {track.name}", file=f)
        except (IOError, OSError) as e:
            if self._write_failed == 0:
                log.error("Writing track list to '%s' failed: %s", self.path, e)
            self._write_failed += 1

    def close(self) -> None:
        pass
