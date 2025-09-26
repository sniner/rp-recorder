from __future__ import annotations

import logging
import pathlib
import re

from datetime import timedelta, time


log = logging.getLogger(__name__)


class CueSheet:
    def __init__(
        self,
        performer: str,
        path: str | pathlib.Path,
    ):
        self.performer: str = performer
        self.path: pathlib.Path = pathlib.Path(path)
        self.filename: str = self.path.stem
        self.track_no: int = 1

    @staticmethod
    def _time(timepos: time | timedelta):
        if isinstance(timepos, timedelta):
            s = int(timepos.total_seconds())
            ms = timepos.microseconds / 1000
            frame = int(ms / 75)
            return f"{s // 60:02d}:{s - 60 * (s // 60):02d}:{frame:02d}"
        else:
            ms = timepos.microsecond / 1000
            frame = int(ms / 75)
            return f"{timepos.hour * 60 + timepos.minute:02d}:{timepos.second:02d}:{frame:02d}"

    def _header(self):
        item = "\n".join(
            [
                f'PERFORMER "{self.performer}"',
                f'FILE "{self.filename}" WAVE',
            ]
        )
        return item

    def _track_entry(
        self, filepos: int, timepos: timedelta, track: str, cover_url: str
    ) -> str:
        if self.track_no > 99:
            self.track_no = 1
            prefix = "\n"
        else:
            prefix = ""
        try:
            performer, title = re.split(r"\s+-\s+", track, maxsplit=1)
        except ValueError:
            performer = ""
            title = track
        item = "\n".join(
            [
                f"  TRACK {self.track_no:02d} AUDIO",
                f'    TITLE "{title}"',
                f'    PERFORMER "{performer}"',
                f"    INDEX 01 {self._time(timepos)}",
                f"    REM FILEPOS {filepos}",
                f'    REM COVER "{cover_url}"',
            ]
        )
        if self.track_no == 1:
            item = prefix + "\n".join([self._header(), item])
        self.track_no += 1
        return item

    def add_track(
        self, filepos: int, timepos: timedelta, track: str, cover_url: str
    ) -> str:
        entry = self._track_entry(filepos, timepos, track, cover_url)
        if self.path:
            with open(self.path, "a") as f:
                print(entry, file=f)
        return entry
