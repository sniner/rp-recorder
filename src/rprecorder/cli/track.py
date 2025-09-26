from __future__ import annotations

import argparse
import logging
import pathlib
import signal
import threading

from rprecorder import config, tracker, utils


log = logging.getLogger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__
    )

    parser.add_argument("--logfile", type=pathlib.Path, help="Log file path")
    parser.add_argument("--verbose", action="store_true", help="Set log level to DEBUG")
    parser.add_argument("--config", help="TOML file with tracking configuration")

    return parser.parse_args()


def main():
    args = parse_arguments()

    utils.setup_logger(
        logfile=args.logfile,
        loglevel=logging.DEBUG if args.verbose else logging.INFO,
    )

    trackers: list[tracker.RPTrackRecorder] = []
    threads: list[threading.Thread] = []
    stop_event: threading.Event = threading.Event()

    def signal_handler(sig, frame):
        log.debug("Signal received, stopping now!")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        conf = config.load_config(args.config or config.DEFAULT_CONFIG_FILE)

        log.info("START")

        conf.tracking.database.parent.mkdir(parents=True, exist_ok=True)

        trackers = tracker.create(conf.tracking, conf.channels)
        threads = [threading.Thread(target=t.record, daemon=False) for t in trackers]
        for t in threads:
            t.start()

        while not stop_event.is_set():
            stop_event.wait(1.0)

        for tr in trackers:
            tr.stop()
        for t in threads:
            t.join(timeout=5)
    except Exception as exc:
        log.error("Fatal error: %s", exc)
    except KeyboardInterrupt:
        log.warning("Interrupted!")
    finally:
        log.info("FINISHED")


if __name__ == "__main__":
    main()
