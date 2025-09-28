from __future__ import annotations

import logging
import re
import time

from dataclasses import dataclass
from typing import Generator

import urllib3

from rprecorder import config


log = logging.getLogger(__name__)


USER_AGENT = "RPStreamRecorder/1.0 (+contact: your-email@example.com)"

_connection_pool = urllib3.PoolManager(retries=False)


@dataclass
class StreamChunk:
    timestamp: float
    audio_data: bytes
    meta_data: dict[str, str]


_meta_sq = re.compile(r"(\w+)='([^']*)'")
_meta_dq = re.compile(r'(\w+)="([^"]*)"')


# Example:
# b"StreamTitle='Led Zeppelin - Kashmir';StreamUrl='http://img.radioparadise.com/covers/l/B000002JSN.jpg';\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
def _parse_metablock(meta: bytes) -> dict[str, str]:
    raw = meta.rstrip(b"\x00")
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        s = raw.decode("latin-1", errors="replace")
    # Primär: Shoutcast-Standard mit einfachen Quotes
    items = _meta_sq.findall(s)
    if not items:
        items = _meta_dq.findall(s)
    return {k.lower().strip(): v.strip() for k, v in items}


class ShoutcastReader:
    def __init__(self, stream: config.StreamCfg):
        self.stream = stream
        self._active = False
        self._conn: urllib3.BaseHTTPResponse | None = None

    def stop(self) -> None:
        self._active = False
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None

    def _read_block(self, conn: urllib3.BaseHTTPResponse, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = conn.read(n - len(buf))
            except Exception as e:
                log.debug("[%s] read aborted: %s", self.stream.channel.name, e)
                return b""
            if not chunk:
                logging.warning("[%s] Stream ended/EOF", self.stream.channel.name)
                return b""
            buf += chunk
        return bytes(buf)

    def read_stream(self) -> Generator[StreamChunk, None, None]:
        conn = _connection_pool.request(
            "GET",
            self.stream.url,
            preload_content=False,
            headers={"Icy-MetaData": "1", "User-Agent": USER_AGENT},
            timeout=urllib3.Timeout(connect=10.0, read=60.0),
            redirect=True,
        )
        self._conn = conn
        if conn.status != 200:
            logging.error(
                "[%s] Request failed, status: %s", self.stream.channel.name, conn.status
            )
            conn.close()
            self._conn = None
            return

        metaint = conn.headers.get("icy-metaint")
        try:
            blocksize = int(metaint) if metaint else 0
        except ValueError:
            blocksize = 0
        if blocksize <= 0:
            logging.error("[%s] No embedded metadata", self.stream.channel.name)
            conn.close()
            self._conn = None
            return
        logging.debug(
            "[%s] Stream blocksize: %d bytes", self.stream.channel.name, blocksize
        )

        self._active = True
        start_time: float = time.monotonic()
        block_time: float = 0.0
        try:
            with conn:
                while self._active:
                    block_time = time.monotonic() if block_time else start_time
                    audio = self._read_block(conn, blocksize)
                    if not audio:
                        return
                    metalen = self._read_block(conn, 1)
                    if not metalen:
                        return
                    mlen = metalen[0] * 16
                    if mlen > 0:
                        meta_data = self._read_block(conn, mlen)
                        if not meta_data:
                            return
                        meta = _parse_metablock(meta_data)
                    else:
                        meta = {}
                    yield StreamChunk(
                        timestamp=block_time - start_time,
                        audio_data=audio,
                        meta_data=meta,
                    )
        finally:
            self._conn = None
            self._active = False
