from __future__ import annotations

import json
import logging
import pathlib
import sqlite3
import sys
import time
import threading

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generator, Iterable, Mapping, NotRequired, Sequence, TypedDict

from rprecorder import config

import requests


logger = logging.getLogger(__name__)

# About Radio Paradise API:
#
# * https://github.com/marco79cgn/radio-paradise
# * http://moodeaudio.org/forum/showthread.php?tid=2172&page=2


Params = Sequence[Any] | Mapping[str, Any]


class RPTrackDatabase:
    def __init__(self, path: pathlib.Path, channels: Sequence[config.ChannelCfg] = ()):
        self.path = path
        self.channels = channels
        self._connection: sqlite3.Connection | None = None
        self._lock: threading.Lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA busy_timeout=5000;")  # 5s
            self._setup(
                conn,
            )
            self._connection = conn
        return self._connection

    def _close(self):
        if self._connection:
            self._connection.close()
            self._connection = None

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        yield self._connect()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Serialisierte Transaktion: BEGIN/COMMIT/ROLLBACK."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _exec(self, sql: str, params: Params = ()) -> None:
        """Helper for writing operations (INSERT/UPDATE/DELETE)."""
        with self.transaction() as conn:
            conn.execute(sql, params)

    def _query_one(self, sql: str, params: Params = ()) -> sqlite3.Row | None:
        """Helper for reading operations, only one row as result."""
        with self._lock:
            conn = self._connect()
            return conn.execute(sql, params).fetchone()

    def _query_all(self, sql: str, params: Params = ()) -> Sequence[sqlite3.Row]:
        """Helper for reading operations, all rows as result."""
        with self._lock:
            conn = self._connect()
            return conn.execute(sql, params).fetchall()

    def sync_channels(self, items: list[tuple[int, str]]) -> None:
        # benötigt SQLite mit UPSERT (üblich seit 3.24)
        sql = """
        INSERT INTO channels(channel, name) VALUES(?, ?)
        ON CONFLICT(channel) DO UPDATE SET name=excluded.name
        """
        with self.transaction() as conn:
            conn.executemany(sql, items)

    def _setup(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                track  INTEGER PRIMARY KEY,
                artist TEXT NOT NULL,
                title  TEXT NOT NULL,
                album  TEXT NOT NULL,
                year   INTEGER NOT NULL,
                cover  TEXT,
                UNIQUE (artist, title, album, year) ON CONFLICT IGNORE
            )
        """)
        # conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_1 ON tracks(track)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                time    TEXT NOT NULL,
                channel INTEGER NOT NULL,
                track INTEGER NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_playlists_1 ON playlists(time, channel)"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS played (
                channel INTEGER NOT NULL,
                track   INTEGER NOT NULL,
                PRIMARY KEY (channel, track) ON CONFLICT IGNORE
            ) WITHOUT ROWID
        """)
        # conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_played_1 ON played(channel, track)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel INTEGER PRIMARY KEY,
                name    TEXT NOT NULL,
                UNIQUE (channel, name) ON CONFLICT IGNORE
            )
        """)
        # conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_1 ON channels(channel)")

        conn.execute("""
            CREATE VIEW IF NOT EXISTS played_view AS
            SELECT
                p.time                 AS played_time,
                c.name                 AS channel_name,
                t.track                AS track_id,
                t.artist,
                t.title,
                t.album,
                t.year,
                t.cover
            FROM playlists AS p
            JOIN tracks   AS t ON t.track   = p.track
            JOIN channels AS c ON c.channel = p.channel
            ORDER BY p.time ASC;
        """)

        with conn:
            conn.executemany(
                """
                INSERT INTO channels(channel, name) VALUES(?, ?)
                ON CONFLICT(channel) DO UPDATE SET name=excluded.name
            """,
                [(c.id, c.name) for c in self.channels],
            )

    def checkpoint(self, mode: str = "FULL") -> tuple[int, int, int]:
        """Modes: PASSIVE | FULL | RESTART | TRUNCATE"""
        with self.connect() as conn:
            # gibt (busy, log, ckpt) zurück, aber Python sqlite3 liefert Rows
            row = conn.execute(f"PRAGMA wal_checkpoint({mode});").fetchone()
            return tuple(row)  # type: ignore

    @staticmethod
    def row_to_dict(row: sqlite3.Row) -> dict:
        return {k: row[k] for k in row.keys()}

    def get_track(self, artist, title, album, year) -> sqlite3.Row | None:
        return self._query_one(
            "SELECT * FROM tracks WHERE artist=? AND title=? AND album=? AND year=?",
            (artist, title, album, year),
        )

    def get_tracks(self, channel: int | None = None) -> Sequence[sqlite3.Row]:
        if channel:
            return self._query_all(
                "SELECT t.* FROM tracks AS t "
                "INNER JOIN played AS p ON p.track=t.track "
                "WHERE p.channel=?",
                (channel,),
            )
        else:
            return self._query_all("SELECT * FROM tracks")

    def add_track(
        self, artist: str, title: str, album: str, year: int, cover: str = ""
    ):
        self._exec(
            "INSERT OR IGNORE INTO tracks(artist, title, album, year, cover) "
            "VALUES (?, ?, ?, ?, ?)",
            (artist, title, album, year, cover),
        )

    def add_played(self, channel: int, track: int):
        self._exec(
            "INSERT OR IGNORE INTO played(channel, track) VALUES (?, ?)",
            (channel, track),
        )

    def set_cover(self, track: int, cover: str):
        self._exec("UPDATE tracks SET cover=? WHERE track=?", (cover, track))

    def add_to_playlist(self, channel: int, track: int):
        last = self._query_one(
            "SELECT track FROM playlists WHERE channel=? ORDER BY time DESC LIMIT 1",
            (channel,),
        )
        if last is None or last["track"] != track:
            self._exec(
                "INSERT OR IGNORE INTO playlists(time, channel, track) VALUES (?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    channel,
                    track,
                ),
            )


@dataclass
class RPTrack:
    artist: str
    title: str
    album: str
    year: int
    cover: str

    @staticmethod
    def from_api(d: dict[str, Any]) -> RPTrack | None:
        # Pflichtfelder prüfen
        for key in ("artist", "title", "album"):
            if not d.get(key):
                return None
        # year robust parsen
        year_raw = d.get("year", 0)
        try:
            year = int(year_raw)
        except Exception:
            year = 0
        cover = str(d.get("cover") or "")
        return RPTrack(
            artist=str(d["artist"]),
            title=str(d["title"]),
            album=str(d["album"]),
            year=year,
            cover=cover,
        )


class RPTrackRecorder:
    def __init__(self, db: RPTrackDatabase, channel: int):
        self.db = db
        self.channel = int(channel) if channel is not None else 0
        self.active = True
        self._cancel = threading.Event()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "RPTrackRecorder/1.0 (+contact: your-email@example.com)",
                "Accept": "application/json",
            }
        )

    def stop(self) -> None:
        self.active = False
        self._cancel.set()

    def _api_url(self, n: int) -> str:
        return f"https://api.radioparadise.com/api/now_playing?chan={n}"

    def _fetch_now_playing(self, timeout: float = 10.0) -> dict[str, Any] | None:
        """Holt JSON; gibt None bei Fehlern zurück (wir backoffen dann)."""
        url = self._api_url(self.channel)
        try:
            resp = self._session.get(url, timeout=timeout)
            if resp.status_code != 200:
                logger.warning(
                    "Channel %s: Got HTTP %s from API", self.channel, resp.status_code
                )
                return None
            return resp.json()  # type: ignore[no-any-return]
        except requests.RequestException as e:
            logger.warning("Channel %s: Request error: %s", self.channel, e)
            return None
        except ValueError as e:
            logger.warning("Channel %s: Invalid JSON response: %s", self.channel, e)
            return None

    def _track_stream(self, base_wait: int = 30) -> Generator[RPTrack, None, None]:
        """
        Generator liefert RPTrack-Dicts, wenn sich der 'now playing' Eintrag ändert.
        Wartet gemäß 'time' (falls vorhanden), minimal 5s.
        """
        current: dict[str, Any] = {}
        backoff = 1.0  # Sekunden, exponentiell bei API-Fehlern

        while self.active:
            payload = self._fetch_now_playing()
            if not payload:
                # Backoff bei API-Fehlern, capped
                wait = min(max(1.0, backoff), 60.0)
                logger.info("Channel %s: API down? Waiting %.1fs", self.channel, wait)
                self._cancel.wait(wait)
                backoff = min(backoff * 2.0, 60.0)
                continue

            # Reset des Backoffs nach erfolgreichem Fetch
            backoff = 1.0

            # Dauer bis zum nächsten Poll
            duration = base_wait
            t = payload.get("time")
            if t is not None:
                try:
                    duration = max(5, int(t) + 1)
                except Exception:
                    duration = base_wait
                del payload["time"]

            # Gleichheit checken auf dem rohen Payload (stabil genug für unseren Zweck)
            if payload != current:
                current = payload
                track = RPTrack.from_api(payload)
                if track is not None:
                    yield track
                else:
                    logger.debug(
                        "Channel %s: unvollständiger Track: %s", self.channel, payload
                    )

            logger.info("Channel %s: Waiting for %s seconds", self.channel, duration)
            self._cancel.wait(duration)

    def _record_once(self) -> None:
        """Verarbeitet neue 'now playing' Items, bis stop() aufgerufen wird."""
        for track in self._track_stream():
            row = self.db.get_track(track.artist, track.title, track.album, track.year)
            if row is None:
                self.db.add_track(
                    track.artist, track.title, track.album, track.year, track.cover
                )
                row = self.db.get_track(
                    track.artist, track.title, track.album, track.year
                )

            if not row:
                logger.warning("Channel %s: Failed to read/add title", self.channel)
                continue

            track_id = row["track"]
            cover_url_db = row["cover"]

            logger.info(
                "Channel %s: Now playing: #%s: %s", self.channel, track_id, dict(row)
            )

            # played & playlist
            self.db.add_played(self.channel, track_id)
            self.db.add_to_playlist(self.channel, track_id)

            # Update cover if necessary
            if (track.cover or "") and track.cover != cover_url_db:
                logger.info(
                    "Channel %s: Updating cover url on #%s", self.channel, track_id
                )
                self.db.set_cover(track_id, track.cover)

    def record(self) -> None:
        logger.info("Channel %s: tracking started", self.channel)
        self.active = True
        while self.active:
            try:
                self._record_once()
            except Exception as exc:
                logger.error(
                    "Channel %s: Exception occured: %s",
                    self.channel,
                    exc,
                    exc_info=True,
                )
                self._cancel.wait(10)
        logger.info("Channel %s: tracking stopped", self.channel)


def create(
    conf: config.TrackingCfg,
    channels: Sequence[config.ChannelCfg],
) -> list[RPTrackRecorder]:
    db = RPTrackDatabase(pathlib.Path(conf.database), channels)
    return [RPTrackRecorder(db, channel.id) for channel in channels]
