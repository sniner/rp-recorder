from __future__ import annotations

import logging
import pathlib
import tomllib

from dataclasses import dataclass
from typing import Any


DEFAULT_CONFIG_FILE = "radioparadise.toml"
DEFAULT_RECORDINGS_DIR = "./recordings"
DEFAULT_DATABASE_PATH = "./rp-tracks.db"
DEFAULT_CONTACT = "contact@example.com"


log = logging.getLogger(__name__)


@dataclass
class ChannelCfg:
    id: int
    name: str


@dataclass
class TrackingCfg:
    url: str  # e.g. "https://...now_playing?chan=%s" oder "...?chan={chan}"
    contact: str  # for User-Agent
    database: pathlib.Path  # SQLite database path


@dataclass
class RecordingCfg:
    output: pathlib.Path
    cuesheet: bool = False
    tracklist: bool = True


@dataclass
class StreamCfg:
    channel: ChannelCfg
    url: str
    type: str
    cuesheet: bool | None = None
    tracklist: bool | None = None


@dataclass
class AppConfig:
    channels: list[ChannelCfg]
    tracking: TrackingCfg
    recording: RecordingCfg
    streams: list[StreamCfg]


def _coerce_url_template(s: str) -> str:
    # %s → {chan}, damit klarer
    return s.replace("%s", "{chan}")


def load_config(path: str | pathlib.Path) -> AppConfig:
    data: dict[str, Any]
    with open(path, "rb") as f:
        data = tomllib.load(f)

    ch = [ChannelCfg(**c) for c in data.get("channels", [])]
    ch_map = {c.id: c for c in ch}
    tr_raw = data.get("tracking", {})
    tr = TrackingCfg(
        url=_coerce_url_template(tr_raw["url"]),
        contact=tr_raw.get("contact", DEFAULT_CONTACT),
        database=pathlib.Path(tr_raw.get("database", DEFAULT_DATABASE_PATH)),
    )
    rec_raw = data.get("recording", {})
    rec = RecordingCfg(
        output=pathlib.Path(rec_raw.get("output", DEFAULT_RECORDINGS_DIR)),
        cuesheet=bool(rec_raw.get("cuesheet", False)),
        tracklist=bool(rec_raw.get("tracklist", True)),
    )
    st_raw = data.get("streams", [])
    streams: list[StreamCfg] = []
    for st in st_raw:
        cid = st["channel"]
        if cid not in ch_map:
            log.error("Definition for channel #%s missing!", cid)
        s = StreamCfg(
            channel=ch_map[cid],
            url=st["url"],
            type=st["type"],
            cuesheet=bool(st.get("cuesheet") or rec.cuesheet),
            tracklist=bool(st.get("tracklist") or rec.tracklist),
        )
        streams.append(s)

    return AppConfig(channels=ch, tracking=tr, recording=rec, streams=streams)
