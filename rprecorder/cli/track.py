#!/usr/bin/python3

import json
import logging
import signal
import sqlite3
import sys
import time
import threading

from datetime import datetime

import requests


logger = logging.getLogger(__name__)

# Radio Paradise API:
#
# * https://github.com/marco79cgn/radio-paradise
# * http://moodeaudio.org/forum/showthread.php?tid=2172&page=2

class RPTrackDatabase:
    def __init__(self, path=None):
        self.connection = None
        self.path = path
        self.lock = threading.Lock()
        if path:
            self._open()
            self._setup()

    def _open(self):
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

    def _close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def _setup(self):
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS tracks
            (track INTEGER PRIMARY KEY,
            artist TEXT NOT NULL,
            title TEXT NOT NULL,
            album TEXT NOT NULL,
            year INTEGER NOT NULL,
            cover TEXT,
            UNIQUE (artist, title, album, year) ON CONFLICT IGNORE)
        """)
        self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_1 ON tracks(track)")
        # self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_2 ON tracks(artist, title, album, year)")

        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS playlists
            (time TEXT NOT NULL, channel INTEGER NOT NULL, track INTEGER NOT NULL)
        """)
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_playlists_1 ON playlists(time, channel)")

        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS played
            (channel INTEGER NOT NULL,
            track INTEGER NOT NULL,
            PRIMARY KEY (channel, track) ON CONFLICT IGNORE)
            WITHOUT ROWID
        """)
        # self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_played_1 ON played(channel, track)")

        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS channels
            (channel INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            UNIQUE (channel, name) ON CONFLICT IGNORE)
        """)
        self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_1 ON channels(channel)")

        with self.connection:
            self.connection.execute("""
                INSERT OR IGNORE INTO channels(channel, name) VALUES
                (0, 'Main'),
                (1, 'Mellow'),
                (2, 'Rock'),
                (3, 'World/Etc')
            """)
    
    def row_to_dict(self, row:sqlite3.Row) -> dict:
        return {k:row[k] for k in row.keys()}

    def open(self, path):
        self._close()
        self.path = path
        self._open()
        self._setup()
        return self

    def close(self):
        self._close()
        return self

    def query(self, statement, *args):
        with self.lock:
            return self.connection.execute(statement, *args)

    def commit(self, statement, *args):
        with self.lock:
            with self.connection:
                self.connection.execute(statement, *args)

    def get_track(self, artist, title, album, year):
        return self.query(
            "SELECT * FROM tracks WHERE artist=? AND title=? AND album=? AND year=?",
            (artist, title, album, year)
        ).fetchone()

    def get_tracks(self, channel:int=None):
        if channel:
            return self.query(
                "SELECT t.* FROM tracks AS t INNER JOIN played AS p ON p.track=t.track WHERE p.channel=?",
                (channel,)
            ).fetchall()
        else:
            return self.query("SELECT * FROM tracks").fetchall()

    def add_track(self, artist:str, title:str, album:str, year:int, cover:str=""):
        self.commit(
            "INSERT OR IGNORE INTO tracks(artist, title, album, year, cover) VALUES (?, ?, ?, ?, ?)",
            (artist, title, album, year, cover),
        )

    def add_played(self, channel:int, track:int):
        self.commit(
            "INSERT OR IGNORE INTO played(channel, track) VALUES (?, ?)",
            (channel, track)
        )

    def set_cover(self, track:int, cover:str):
        self.commit("UPDATE tracks SET cover=? WHERE track=?", (cover, track))

    def add_to_playlist(self, channel:int, track:int):
        row = self.query(
            "SELECT track FROM playlists WHERE channel=? ORDER BY time DESC LIMIT 1",
            (channel,)
        ).fetchone()
        if row is None or row["track"]!=track:
            self.commit(
                "INSERT OR IGNORE INTO playlists(time, channel, track) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), channel, track)
            )


class RPTrackRecorder:
    def __init__(self, db, channel, lock=None):
        self.db = db
        self.channel = channel or 0
        self.active = True

    def stop(self):
        self.active = False

    def _api_url(self, n):
        return f"https://api.radioparadise.com/api/now_playing?chan={n}"

    def _track_playing(self, wait=30):
        url = self._api_url(self.channel)
        current = {}
        while self.active:
            r = requests.get(url)
            if r.status_code==200:
                playing = json.loads(r.text)
                if "time" in playing:
                    try:
                        duration = max(5, int(playing["time"])+1)
                    except:
                        duration = wait
                    del playing["time"]
                else:
                    duration = wait
                if "year" in playing:
                    try:
                        playing["year"] = int(playing["year"])
                    except:
                        playing["year"] = 0
                playing["channel"] = self.channel
                if playing!=current:
                    current = playing
                    yield current
            logger.info(f"Channel {self.channel}: Waiting for {duration} seconds")
            time.sleep(duration)

    def _record(self):
        for track in self._track_playing():
            row = self.db.get_track(track['artist'], track['title'], track['album'], track['year'])
            if row is None:
                self.db.add_track(track["artist"], track["title"], track["album"], track["year"], track["cover"])
                row = self.db.get_track(track['artist'], track['title'], track['album'], track['year'])
            if row:
                track_id, cover_url = row["track"], row["cover"]
                logger.info(f"Channel {self.channel}: Now playing: #{track_id}: {dict(row)}")
                self.db.add_played(self.channel, track_id)
                if cover_url!=track["cover"]:
                    logger.info(f"Channel {self.channel}: Updating cover url on {track_id}")
                    self.db.set_cover(track_id, cover_url)
                self.db.add_to_playlist(self.channel, track_id)                
            else:
                logger.warning(f"Channel {self.channel}: Unable to retrieve/insert title record")

    def record(self):
        logger.info(f"Channel {self.channel}: tracking started")
        self.active = True
        while self.active:
            try:
                self._record()
            except Exception as exc:
                logger.error(f"Channel {self.channel}: Exception occured: {exc}", exc_info=True)
            time.sleep(10)
        logger.info(f"Channel {self.channel}: tracking stopped")


def record(path:str, daemon:bool=True):
    db = RPTrackDatabase(path)
    tracker = [RPTrackRecorder(db, channel) for channel in range(4)]
    threads = [threading.Thread(target=t.record, daemon=daemon) for t in tracker]
    for t in threads:
        t.start()
    return db, tracker, threads


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s -- %(message)s")

    db, _tracker, _threads = record("rp_tracks.db")

    def signal_handler(sig, frame):
        logger.warning("Signal received, stopping now!")
        db.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.pause()


if __name__=="__main__":
    main()

# vim: set et sw=4 ts=4 ft=python:
