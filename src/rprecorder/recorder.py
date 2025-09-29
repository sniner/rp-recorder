from __future__ import annotations

import logging
import pathlib
import re
import threading

from datetime import datetime, timedelta
from enum import StrEnum

from rprecorder import config, shoutcast, writer

from .track import TrackInfo

log = logging.getLogger(__name__)


class CutMode(StrEnum):
    IMMEDIATE = "immediate"
    ON_TRACK = "on-track"


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
        self._meta_writer: list[writer.Writer] = []

    def _channel_to_filename(self) -> str:
        s = re.sub(r"[^\w\d_\-\.\(\)\[\]]", "_", self.stream.channel.name)
        s = re.sub(r"__+", "_", s)
        return s

    def _track_info(
        self, filepos: int, timepos: float, meta: dict[str, str]
    ) -> TrackInfo:
        return TrackInfo(
            filepos=filepos,
            timepos=timepos,
            name=meta.get("streamtitle", ""),
            cover=meta.get("streamurl", ""),
        )

    def _create_writer(self, audiofile: pathlib.Path) -> list[writer.Writer]:
        wr: list[writer.Writer] = []
        if self.stream.cuesheet:
            wr.append(
                writer.CueSheetWriter(
                    performer=self.stream.channel.name,
                    audiofilename=audiofile.name,
                    path=audiofile.with_suffix(".cue"),
                )
            )
        if self.stream.tracklist:
            wr.append(writer.TrackListWriter(path=audiofile.with_suffix(".txt")))
        if self.recording.matroska:
            wr.append(
                writer.ChapterFileWriter(
                    path=audiofile.with_suffix(".xml"),
                    edition_name=self.stream.channel.name,
                )
            )
        return wr

    def _write_metadata(self, track: TrackInfo) -> None:
        for w in self._meta_writer:
            w.add_track(track)
        logging.info(
            "[%s] Recording: %r @ %s",
            self.stream.channel.name,
            track.name,
            track.timepos_str(),
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

        self._meta_writer = self._create_writer(audio_file)

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
                            ti = self._track_info(
                                filepos=filepos,
                                timepos=chunk.timestamp - record_start_time,
                                meta=chunk.meta_data,
                            )
                            meta_thread = threading.Thread(
                                target=self._write_metadata,
                                args=(ti,),
                                daemon=True,
                            ).start()
                        else:
                            ti = self._track_info(0, 0.0, chunk.meta_data)
                            logging.info(
                                "[%s] Skipping: %r",
                                self.stream.channel.name,
                                ti.name,
                            )
                    if recording_started:
                        filepos += target.write(chunk.audio_data)
        finally:
            source.stop()
            if meta_thread:
                meta_thread.join()

            for w in self._meta_writer:
                w.close()
            if filepos == 0:
                for w in self._meta_writer:
                    w.remove()
                if audio_file.exists():
                    audio_file.unlink()


def create(
    recording: config.RecordingCfg,
    streams: list[config.StreamCfg],
    output: pathlib.Path,
) -> list[RPRecorder]:
    return [RPRecorder(recording, stream, output) for stream in streams]
