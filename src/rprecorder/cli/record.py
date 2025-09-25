from __future__ import annotations

import argparse
import logging
import pathlib
import threading

from dataclasses import dataclass
from datetime import datetime, timedelta

from rprecorder import config, recorder, utils


log = logging.getLogger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__
    )

    parser.add_argument("--logfile", type=pathlib.Path, help="Log file path")
    parser.add_argument("--verbose", action="store_true", help="Set log level to DEBUG")
    parser.add_argument(
        "--config",
        required=True,
        help="TOML file with recording configuration",
    )
    parser.add_argument("--output", type=pathlib.Path, help="Output directory")

    duration_parser = parser.add_mutually_exclusive_group()
    duration_parser.add_argument(
        "--duration", type=int, help="How many seconds to record"
    )
    duration_parser.add_argument(
        "--until",
        type=utils.parse_datetime_arg,
        help="Record until specified datetime ('yyyy-mm-dd hh:mm[:ss]' or 'hh:mm[:ss]')",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    utils.setup_logger(
        logfile=args.logfile,
        loglevel=logging.DEBUG if args.verbose else logging.INFO,
    )
    log.info("START")

    try:
        conf = config.load_config(args.config or config.DEFAULT_CONFIG_FILE)

        output_dir: pathlib.Path = args.output or conf.recording.output
        output_dir.mkdir(parents=True, exist_ok=True)

        if args.until:
            end_time = args.until
        else:
            start_time = datetime.now()
            end_time = start_time + timedelta(seconds=args.duration or 60)
        log.info("Recording until %s into %r", end_time, str(output_dir.absolute()))

        recorders = recorder.create(conf.streams, output_dir, end_time)
        threads = [threading.Thread(target=r.record, daemon=True) for r in recorders]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    except Exception as exc:
        log.error("Fatal error: %s", exc)
    except KeyboardInterrupt:
        log.warning("Interrupted!")
    finally:
        log.info("FINISHED")


if __name__ == "__main__":
    main()


# vim: set et sw=4 ts=4:
