from __future__ import annotations

import logging
import pathlib

from datetime import timedelta

from .common import TrackInfo, Writer


log = logging.getLogger(__name__)


class CueSheetWriter(Writer):
    def __init__(
        self,
        performer: str,
        audiofilename: str,
        path: str | pathlib.Path,
    ):
        super().__init__(path=path)
        self.performer: str = performer
        self.filename: str = audiofilename
        self.track_no: int = 1
        self._write_failed: int = 0

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

    def _track_entry(self, track: TrackInfo) -> str:
        if self.track_no > 99:
            self.track_no = 1
            prefix = "\n"
        else:
            prefix = ""

        try:
            artist, title = track.artist_title()
        except ValueError:
            artist = ""
            title = track
        item = "\n".join(
            [
                f"  TRACK {self.track_no:02d} AUDIO",
                f'    TITLE "{title}"',
                f'    PERFORMER "{artist}"',
                f"    INDEX 01 {self._time(track.timepos)}",
                f"    REM FILEPOS {track.filepos}",
                f'    REM COVER "{track.cover}"',
            ]
        )
        if self.track_no == 1:
            item = prefix + "\n".join([self._header(), item])
        self.track_no += 1
        return item

    def add_track(self, track: TrackInfo) -> None:
        entry = self._track_entry(track)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                print(entry, file=f)
        except (IOError, OSError) as e:
            if self._write_failed == 0:
                log.error("Writing cuesheet to '%s' failed: %s", self.path, e)
            self._write_failed += 1

    def close(self) -> None:
        pass
