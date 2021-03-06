import logging
import pathlib
import re

from datetime import datetime, timedelta, time
from typing import Union


log = logging.getLogger(__name__)


class CueSheet:
    def __init__(self, performer:str, filename:pathlib.Path, path:Union[str,pathlib.Path]=None):
        self.performer = performer
        self.filename = filename
        self.track_no = 1
        self.path = path

    @staticmethod
    def _time(timepos:Union[time,timedelta]):
        if isinstance(timepos, timedelta):
            s = int(timepos.total_seconds())
            ms = timepos.microseconds/1000
            frame = int(ms/75)
            return f"{s//60:02d}:{s-60*(s//60):02d}:{frame:02d}"
        else:
            ms = timepos.microsecond/1000
            frame = int(ms/75)
            return f"{timepos.hour*60+timepos.minute:02d}:{timepos.second:02d}:{frame:02d}"

    def _header(self):
        item = "\n".join([
            f'PERFORMER "{self.performer}"',
            f'FILE "{self.filename}" WAVE',
        ])
        return item

    def _add_track(self, filepos:int, timepos:datetime, meta:dict):
        if self.track_no>99:
            self.track_no = 1
            prefix = "\n"
        else:
            prefix = ""
        try:
            performer, title = re.split(r"\s+-\s+", meta.get("streamtitle", ""), maxsplit=1)
        except ValueError:
            performer = ""
            title = meta.get("streamtitle", "")
        cover = meta.get("streamurl", "")
        item = "\n".join([
            f'  TRACK {self.track_no:02d} AUDIO',
            f'    TITLE "{title}"',
            f'    PERFORMER "{performer}"',
            f'    INDEX 01 {self._time(timepos)}',
            f'    REM FILEPOS {filepos}',
            f'    REM COVER "{cover}"',
        ])
        if self.track_no==1:
            item = prefix + "\n".join([self._header(), item])
        self.track_no += 1
        return item

    def add_track(self, filepos:int, timepos:datetime, meta:dict):
        item = self._add_track(filepos, timepos, meta)
        if self.path:
            with open(self.path, "a") as f:
                print(item, file=f)
        return item