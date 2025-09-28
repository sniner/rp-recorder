from __future__ import annotations

import logging
import pathlib
import re

from datetime import timedelta


log = logging.getLogger(__name__)


class CueSheet:
    def __init__(
        self,
        performer: str,
        audiofilename: str,
        path: str | pathlib.Path,
    ):
        self.performer: str = performer
        self.filename: str = audiofilename
        self.path: pathlib.Path = pathlib.Path(path)
        self.track_no: int = 1

    @staticmethod
    def _time(pos: float | timedelta) -> str:
        if isinstance(pos, timedelta):
            total_frames = (pos.days * 86400 + pos.seconds) * 75 + (
                pos.microseconds * 75
            ) // 1_000_000
        else:
            total_frames = int(pos * 75)

        mm = total_frames // (75 * 60)
        ss = (total_frames // 75) % 60
        ff = total_frames % 75
        return f"{mm:02d}:{ss:02d}:{ff:02d}"

    def _header(self):
        item = "\n".join(
            [
                f'PERFORMER "{self.performer}"',
                f'FILE "{self.filename}" WAVE',
            ]
        )
        return item

    def _track_entry(
        self, filepos: int, timepos: float, track: str, cover_url: str
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
        self, filepos: int, timepos: float, track: str, cover_url: str
    ) -> str:
        entry = self._track_entry(filepos, timepos, track, cover_url)
        if self.path:
            with open(self.path, "a") as f:
                print(entry, file=f)
        return entry
