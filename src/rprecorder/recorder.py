from __future__ import annotations

import logging
import pathlib
import re
import threading

from datetime import datetime, timedelta

import urllib3

from rprecorder import config, cuesheet


log = logging.getLogger(__name__)


def _parse_meta(metastr: str):
    for item in re.split(r"(?<=');(?=\w+=)", metastr):
        match = re.match(r"(\w+)='(.*)'", item)
        if match:
            yield match.group(1).lower(), match.group(2)


# Example:
# b"StreamTitle='Led Zeppelin - Kashmir';StreamUrl='http://img.radioparadise.com/covers/l/B000002JSN.jpg';\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
def _parse_metablock(meta: bytes) -> dict[str, str]:
    datastr = meta.rstrip(b"\x00").decode(encoding="utf-8", errors="replace")
    return dict(_parse_meta(datastr))


class RPRecorder:
    def __init__(
        self,
        stream: config.StreamCfg,
        target_dir: pathlib.Path,
        end_time: datetime | None = None,
    ):
        self.stream = stream
        self.target_dir = target_dir
        self.end_time = end_time
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

    def _process_metadata(
        self, filepos: int, timepos: timedelta, metablock: bytes
    ) -> None:
        metadata = _parse_metablock(metablock)
        track = metadata.get("streamtitle", "")
        secs = int(timepos.total_seconds())
        h = secs // 3600
        m = (secs - h * 3600) // 60
        s = secs % 60
        tpos = f"{h}:{m:02d}:{s:02d}"
        if self._cue_file:
            _ = self._cue_file.add_track(filepos, timepos, metadata)
        if self._list_file:
            with open(self._list_file, "a") as f:
                print(f"{tpos} -- {track}", file=f)
        logging.info("[%s] Playing: %r @ %s", self.stream.channel.name, track, tpos)

    def record(self):
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

        start_time = datetime.now()

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

        filepos = 0
        try:
            with open(audio_file, "wb") as target:
                while not conn.closed:
                    blocktime = datetime.now()
                    if self.end_time and blocktime >= self.end_time:
                        break
                    audio = self._read_block(conn, blocksize)
                    metalen = self._read_block(conn, 1)[0] * 16
                    if metalen > 0:
                        meta = self._read_block(conn, metalen)
                        timepos = blocktime - start_time
                        threading.Thread(
                            target=self._process_metadata(filepos, timepos, meta),
                            daemon=True,
                        ).start()
                    _ = target.write(audio)
                    filepos += len(audio)
        finally:
            conn.release_conn()


def create(
    streams: list[config.StreamCfg],
    output: pathlib.Path,
    end_time: datetime,
) -> list[RPRecorder]:
    return [RPRecorder(stream, output, end_time) for stream in streams]
