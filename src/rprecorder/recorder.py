from __future__ import annotations

import logging
import pathlib
import re
import threading

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import urllib3

from rprecorder import config, cuesheet


log = logging.getLogger(__name__)


class CutMode(StrEnum):
    IMMEDIATE = "immediate"
    ON_TRACK = "on-track"


@dataclass
class TrackInfo:
    offset: str
    title: str
    cover: str


# Example:
# b"StreamTitle='Led Zeppelin - Kashmir';StreamUrl='http://img.radioparadise.com/covers/l/B000002JSN.jpg';\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
def _parse_metablock(meta: bytes) -> dict[str, str]:
    def split_meta(metastr: str):
        for item in re.split(r"(?<=');(?=\w+=)", metastr):
            match = re.match(r"(\w+)='(.*)'", item)
            if match:
                yield match.group(1).lower(), match.group(2)

    datastr = meta.rstrip(b"\x00").decode(encoding="utf-8", errors="replace")
    return dict(split_meta(datastr))


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

    def _channel_to_filename(self) -> str:
        s = re.sub(r"[^\w\d_\-\.\(\)\[\]]", "_", self.stream.channel.name)
        s = re.sub(r"__+", "_", s)
        return s

    def _read_block(self, conn: urllib3.BaseHTTPResponse, blocksize: int) -> bytes:
        data = b""
        while len(data) < blocksize:
            block = conn.read(blocksize - len(data))
            data += block
        logging.debug(
            "[%s] read_block: %d bytes requested, %d bytes read",
            self.stream.channel.name,
            blocksize,
            len(data),
        )
        return data

    def _track_info(self, timepos: timedelta, metablock: bytes) -> TrackInfo:
        metadata = _parse_metablock(metablock)
        secs = int(timepos.total_seconds())
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
        self, filepos: int, timepos: timedelta, metablock: bytes
    ) -> None:
        t = self._track_info(timepos, metablock)
        if self._cue_file:
            _ = self._cue_file.add_track(filepos, timepos, t.title, t.cover)
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
        pool = urllib3.PoolManager()
        conn = pool.request(
            "GET", self.stream.url, preload_content=False, headers={"icy-metadata": "1"}
        )
        conn.auto_close = False  # pyright: ignore[reportAttributeAccessIssue]
        if conn.status != 200:
            conn.release_conn()
            logging.error(
                "[%s] Request failed, status: %s", self.stream.channel.name, conn.status
            )
            return

        start_mode = start_mode or self.recording.start_mode
        stop_mode = stop_mode or self.recording.stop_mode

        start_time = datetime.now()
        wants_to_stop: bool = False
        recording_started: bool = start_mode == CutMode.IMMEDIATE

        ftime = start_time.strftime("%Y%m%d-%H%M%S")
        fname = f"{self._channel_to_filename()}_{ftime}.{self.stream.type or 'dat'}"
        audio_file = self.target_dir / fname

        blocksize = int(conn.getheader("icy-metaint") or "0")
        if blocksize <= 0:
            logging.warning("[%s] No embedded metadata", self.stream.channel.name)
        else:
            logging.debug(
                "[%s] Stream blocksize: %d bytes", self.stream.channel.name, blocksize
            )

        if self.stream.cuesheet:
            self._cue_file = cuesheet.CueSheet(
                performer=self.stream.channel.name,
                path=audio_file.with_suffix(".cue"),
            )
        if self.stream.tracklist:
            self._list_file = audio_file.with_suffix(".txt")

        filepos: int = 0
        track_no: int = 0
        record_start_time: datetime = start_time
        meta_thread: threading.Thread | None = None
        try:
            with open(audio_file, "wb") as target:
                while not conn.closed:
                    blocktime = datetime.now()
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
                    audio = self._read_block(conn, blocksize)
                    metalen = self._read_block(conn, 1)[0] * 16
                    if metalen > 0:
                        track_no += 1
                        if wants_to_stop:
                            # Track changed, stop requested -> stop now
                            break
                        if not recording_started:
                            if track_no > 1:
                                # Skipped first (partial) track -> now we start recording
                                recording_started = True
                                record_start_time = blocktime
                        meta = self._read_block(conn, metalen)
                        if recording_started:
                            timepos = blocktime - record_start_time
                            meta_thread = threading.Thread(
                                target=self._write_metadata,
                                args=(filepos, timepos, meta),
                                daemon=True,
                            ).start()
                        else:
                            t = self._track_info(timedelta(0), meta)
                            logging.info(
                                "[%s] Skipping: %r",
                                self.stream.channel.name,
                                t.title,
                            )
                    if recording_started:
                        filepos += target.write(audio)
        finally:
            conn.release_conn()

        if meta_thread:
            meta_thread.join()
        if filepos == 0:
            audio_file.unlink()


def create(
    recording: config.RecordingCfg,
    streams: list[config.StreamCfg],
    output: pathlib.Path,
) -> list[RPRecorder]:
    return [RPRecorder(recording, stream, output) for stream in streams]
