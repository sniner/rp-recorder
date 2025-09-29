from __future__ import annotations

import pathlib

from datetime import timedelta
from typing import TextIO

from .common import TrackInfo, Writer


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


class ChapterFileWriter(Writer):
    def __init__(self, path: str | pathlib.Path, edition_name: str | None = None):
        super().__init__(path=path)
        self._fh: TextIO | None = None
        self._chapter_uid: int = 1
        self._edition_name: str | None = edition_name

    @staticmethod
    def _ts_hhmmss_ns(pos: float | timedelta) -> str:
        if isinstance(pos, timedelta):
            total_ns = (
                pos.days * 86400 + pos.seconds
            ) * 1_000_000_000 + pos.microseconds * 1_000
        else:
            # pos = Sekunden als float seit Start
            total_ns = int(pos * 1_000_000_000)
        hh, rem = divmod(total_ns, 3_600 * 1_000_000_000)
        mm, rem = divmod(rem, 60 * 1_000_000_000)
        ss, ns = divmod(rem, 1_000_000_000)
        return f"{hh:02d}:{mm:02d}:{ss:02d}.{ns:09d}"

    def _open_if_needed(self) -> None:
        if self._fh:
            return
        self._fh = open(self.path, "w", encoding="utf-8")
        print('<?xml version="1.0" encoding="UTF-8"?>', file=self._fh)
        print("<Chapters>", file=self._fh)
        print("  <EditionEntry>", file=self._fh)
        if self._edition_name:
            en = _xml_escape(self._edition_name)
            print("    <EditionDisplay>", file=self._fh)
            print(f"      <EditionString>{en}</EditionString>", file=self._fh)
            print("    </EditionDisplay>", file=self._fh)

    def _close(self) -> None:
        if self._fh:
            print("  </EditionEntry>", file=self._fh)
            print("</Chapters>", file=self._fh)
            self._fh.close()
        self._fh = None

    def close(self) -> None:
        self._close()

    def add_track(self, track: TrackInfo) -> None:
        """
        Fügt ein Kapitel hinzu. `track` erwartet "Artist - Title" oder nur "Title".
        """
        self._open_if_needed()
        assert self._fh is not None

        try:
            performer, title = track.artist_title()
            title_disp = title if not performer else f"{performer} — {title}"
        except ValueError:
            title_disp = track.name

        title_disp = _xml_escape(title_disp.strip())

        ts = self._ts_hhmmss_ns(track.timepos)

        uid = self._chapter_uid
        self._chapter_uid += 1

        print("    <ChapterAtom>", file=self._fh)
        print(f"      <ChapterUID>{uid}</ChapterUID>", file=self._fh)
        print(f"      <ChapterTimeStart>{ts}</ChapterTimeStart>", file=self._fh)
        print("      <ChapterDisplay>", file=self._fh)
        print(f"        <ChapterString>{title_disp}</ChapterString>", file=self._fh)
        print("      </ChapterDisplay>", file=self._fh)
        print("    </ChapterAtom>", file=self._fh)

    def __enter__(self):
        self._open_if_needed()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._close()
