from __future__ import annotations

import logging
import pathlib
import re
import threading

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from rprecorder import chapters, config, cuesheet, shoutcast


log = logging.getLogger(__name__)


class CutMode(StrEnum):
    IMMEDIATE = "immediate"
    ON_TRACK = "on-track"


@dataclass
class TrackInfo:
    offset: str
    title: str
    cover: str


class RPRecorder:
    def __init__(
        self,
        recording: config.RecordingCfg,
        stream: config.StreamCfg,
        target_dir: pathlib.Path,
    ):
        self.recording = recording
        self.stream = stream
        self.target_dir = target_dir
        self._cue_file: cuesheet.CueSheet | None = None
        self._list_file: pathlib.Path | None = None
        self._chapter_file: chapters.MkaChapters | None = None

    def _channel_to_filename(self) -> str:
        s = re.sub(r"[^\w\d_\-\.\(\)\[\]]", "_", self.stream.channel.name)
        s = re.sub(r"__+", "_", s)
        return s

    def _track_info(self, timepos: float, metadata: dict[str, str]) -> TrackInfo:
        secs = int(timepos)
        h = secs // 3600
        m = (secs - h * 3600) // 60
        s = secs % 60
        tpos = f"{h}:{m:02d}:{s:02d}"
        return TrackInfo(
            offset=tpos,
            title=metadata.get("streamtitle", ""),
            cover=metadata.get("streamurl", ""),
        )

    def _write_metadata(
        self, filepos: int, timepos: float, meta: dict[str, str]
    ) -> None:
        t = self._track_info(timepos, meta)
        if self._cue_file:
            _ = self._cue_file.add_track(filepos, timepos, t.title, t.cover)
        if self._chapter_file:
            _ = self._chapter_file.add_track(timepos, t.title, t.cover)
        if self._list_file:
            with open(self._list_file, "a") as f:
                print(f"{t.offset} -- {t.title}", file=f)
        logging.info(
            "[%s] Recording: %r @ %s", self.stream.channel.name, t.title, t.offset
        )

    def record(
        self,
        end_time: datetime | None = None,
        start_mode: CutMode | None = None,
        stop_mode: CutMode | None = None,
    ) -> None:
        source = shoutcast.ShoutcastReader(self.stream)

        start_mode = start_mode or self.recording.start_mode
        stop_mode = stop_mode or self.recording.stop_mode

        start_time = datetime.now()
        wants_to_stop: bool = False
        recording_started: bool = start_mode == CutMode.IMMEDIATE

        ftime = start_time.strftime("%Y%m%d-%H%M%S")
        fname = f"{self._channel_to_filename()}_{ftime}.{self.stream.type or 'dat'}"
        audio_file = self.target_dir / fname

        if self.stream.cuesheet:
            self._cue_file = cuesheet.CueSheet(
                performer=self.stream.channel.name,
                audiofilename=fname,
                path=audio_file.with_suffix(".cue"),
            )
        if self.stream.tracklist:
            self._list_file = audio_file.with_suffix(".txt")
        if self.recording.matroska:
            self._chapter_file = chapters.MkaChapters(
                path=audio_file.with_suffix(".xml"),
                edition_name=self.stream.channel.name,
            )

        filepos: int = 0
        track_no: int = 0
        record_start_time: float = 0.0
        meta_thread: threading.Thread | None = None
        try:
            with open(audio_file, "wb") as target:
                for chunk in source.read_stream():
                    blocktime = start_time + timedelta(seconds=chunk.timestamp)
                    if end_time and blocktime >= end_time:
                        if stop_mode == CutMode.IMMEDIATE:
                            break
                        elif not wants_to_stop:
                            if filepos == 0:
                                # Nothing recorded -> stop immediately
                                break
                            else:
                                logging.info(
                                    "[%s] Stopping at track end",
                                    self.stream.channel.name,
                                )
                                wants_to_stop = True
                    if chunk.meta_data:
                        track_no += 1
                        if wants_to_stop:
                            # Track changed, stop requested -> stop now
                            break
                        if not recording_started:
                            if track_no > 1:
                                # Skipped first (partial) track -> now we start recording
                                recording_started = True
                                record_start_time = chunk.timestamp
                        if recording_started:
                            timepos = chunk.timestamp - record_start_time
                            meta_thread = threading.Thread(
                                target=self._write_metadata,
                                args=(filepos, timepos, chunk.meta_data),
                                daemon=True,
                            ).start()
                        else:
                            t = self._track_info(0, chunk.meta_data)
                            logging.info(
                                "[%s] Skipping: %r",
                                self.stream.channel.name,
                                t.title,
                            )
                    if recording_started:
                        filepos += target.write(chunk.audio_data)
        finally:
            source.stop()

            if self._chapter_file:
                self._chapter_file.close()
            if meta_thread:
                meta_thread.join()
            if filepos == 0:
                if audio_file.exists():
                    audio_file.unlink()

            self._chapter_file = None
            self._cue_file = None
            self._list_file = None


def create(
    recording: config.RecordingCfg,
    streams: list[config.StreamCfg],
    output: pathlib.Path,
) -> list[RPRecorder]:
    return [RPRecorder(recording, stream, output) for stream in streams]
