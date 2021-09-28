import logging
import pathlib
import re
import threading

from datetime import datetime, timedelta, time
from typing import Union

import urllib3

from rprecorder import cuesheet

log = logging.getLogger(__name__)


def _parse_meta(metastr:str):
    for item in re.split(r"(?<=');(?=\w+=)", metastr):
        match = re.match(r"(\w+)='(.*)'", item)
        if match:
            yield match.group(1).lower(), match.group(2)

# Example:
# b"StreamTitle='Led Zeppelin - Kashmir';StreamUrl='http://img.radioparadise.com/covers/l/B000002JSN.jpg';\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
def _parse_metablock(meta:bytes) -> dict:
    datastr = meta.rstrip(b"\x00").decode(encoding="utf-8", errors="replace")
    return dict(_parse_meta(datastr))

def _station_to_filename(station:str) -> str:
    s = re.sub(r"[^\w\d_\-\.\(\)\[\]]", "_", station)
    s = re.sub(r"__+", "_", s)
    return s

def record(
        station:str,
        streamurl:str,
        streamtype:str,
        target_dir:pathlib.Path,
        end_time:datetime=None,
        cue_sheet:bool=False,
        track_list:bool=True,
        ):
    def read_block(conn, blocksize):
        data = b""
        while len(data)<blocksize:
            block = conn.read(blocksize-len(data))
            data += block
        logging.debug("[%s] read_block: %d bytes requested, %d bytes read", station, blocksize, len(data))
        return data

    def process_metadata(filepos:int, timepos:datetime, metablock:bytes):
        metadata = _parse_metablock(metablock)
        track = metadata.get("streamtitle", "")
        secs = int(timepos.total_seconds())
        h = secs//3600
        m = (secs - h*3600)//60
        s = secs%60
        tpos = f"{h}:{m:02d}:{s:02d}"
        if cue_data:
            cue_data.add_track(filepos, timepos, metadata)
        if tracks_path:
            with open(tracks_path, "a") as tracks_file:
                print(f"{tpos} -- {track}", file=tracks_file)
        logging.info("[%s] Playing: '%s' @ %s", station, track, tpos)

    pool = urllib3.PoolManager()
    conn = pool.request("GET",streamurl, preload_content=False, headers={"icy-metadata": 1})
    conn.auto_close = False
    if conn.status != 200:
        conn.release_conn()
        logging.error("[%s] Request failed, status: %s", station, conn.status)
        return

    start_time = datetime.now()

    ftime = start_time.strftime("%Y%m%d-%H%M%S")
    fname = f"{_station_to_filename(station)}_{ftime}.{streamtype or 'dat'}"
    path = target_dir / fname

    blocksize = int(conn.getheader("icy-metaint", 0))
    if blocksize<=0:
        logging.warning("[%s] No embedded metadata", station)
    else:
        logging.debug("[%s] Stream blocksize: %d bytes", station, blocksize)

    cue_data = cuesheet.CueSheet(performer=station, filename=path.name, path=path.with_suffix(".cue")) if cue_sheet else None
    tracks_path = path.with_suffix(".txt") if track_list else None

    filepos = 0
    try:
        with open(path, "wb") as target:
            while not conn.closed:
                blocktime = datetime.now()
                if end_time and blocktime>=end_time:
                    break
                audio = read_block(conn, blocksize)
                metalen = read_block(conn, 1)[0] * 16
                if metalen>0:
                    meta = read_block(conn, metalen)
                    timepos = blocktime - start_time
                    threading.Thread(target=process_metadata(filepos, timepos, meta), daemon=True).start()
                target.write(audio)
                filepos += len(audio)
    finally:
        conn.release_conn()
    
