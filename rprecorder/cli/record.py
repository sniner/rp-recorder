import argparse
import logging
import pathlib
import re
import sys
import threading
import yaml

from datetime import datetime, timedelta

from rprecorder import recorder


log = logging.getLogger(__name__)

def _parse_datetime(text:str) -> datetime:
    def _int(s:str) -> int:
        if s:
            return int(s)
        return 0

    try:
        if m:=re.match(r"\s*(\d{4})-(\d{2})-(\d{2})\s+((\d{1,2}):(\d{2})(:(\d{2}))?)?", text):
            args = map(lambda v:_int(v), m.groups()[0:3] + m.groups()[4:7])
            dt = datetime(*args)
        elif m:=re.match(r"\s*(\d{1,2}):(\d{2})(:(\d{2}))?", text):
            args = map(lambda v:_int(v), m.groups()[0:2]+m.groups()[3:4])
            now = datetime.now()
            dt = datetime(now.year, now.month, now.day, *args)
        else:
            raise ValueError
        return dt
    except ValueError:
        msg = f"Given date/time '{text}' not valid. Expected format: [YYYY-MM-DD] HH:MM[:SS]"
        raise argparse.ArgumentTypeError(msg)

def parse_arguments():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)

    parser.add_argument(
        "--logfile",
        type=pathlib.Path,
        help="Log file path"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Set log level to DEBUG"
    )
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        required=True,
        help="YAML file with recording configuration"
    )
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument(
        "--duration",
        type=int,
        help="How many seconds to record"
    )
    duration.add_argument(
        "--until",
        type=_parse_datetime,
        help="Record until specified datetime ('yyyy-mm-dd hh:mm[:ss]' or 'hh:mm[:ss]')"
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("./recordings"),
        help="Output directory"
    )

    return parser.parse_args()


def setup_logger(loglevel=logging.INFO, logfile=None):
    logger_format = '%(asctime)s %(levelname)s -- %(message)s'
    if logfile:
        logging.basicConfig(filename=logfile,
                            level=loglevel,
                            format=logger_format)
    else:
        logging.basicConfig(stream=sys.stderr,
                            level=loglevel,
                            format=logger_format)
    return logging.getLogger(__name__)


def record_worker(config:dict, target_dir:pathlib.Path, end_time:datetime):
    recorder.record(
        station=config["name"],
        streamurl=config["url"],
        streamtype=config.get("type", "mp3"),
        track_list=config.get("tracklist", True),
        cue_sheet=config.get("cuesheet", False),
        target_dir=target_dir,
        end_time=end_time,
    )


def main():
    global log

    args = parse_arguments()

    log = setup_logger(logfile=args.logfile, loglevel=logging.DEBUG if args.verbose else logging.INFO)
    log.info('START')

    try:
        with open(args.config) as conf:
            config = yaml.safe_load(conf)
        if isinstance(config, dict):
            config = [config]

        args.output.mkdir(parents=True, exist_ok=True)

        if args.until:
            end_time = args.until
        else:
            start_time = datetime.now()
            end_time = start_time + timedelta(seconds=args.duration or 60)
        log.info("Recording until %s", end_time)

        worker = [threading.Thread(target=record_worker, args=(job, args.output, end_time), daemon=True) for job in config]
        for w in worker:
            w.start()
        for w in worker:
            w.join()
    except Exception as exc:
        log.error("Fatal error: %s", exc)
    except KeyboardInterrupt:
        log.warning("Interrupted!")
    finally:
        log.info("FINISHED")


if __name__ == "__main__":
    main()


# vim: set et sw=4 ts=4: