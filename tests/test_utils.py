import argparse
from datetime import datetime

import pytest
from freezegun import freeze_time

from rprecorder import utils


@freeze_time("2025-09-24 13:00:00")
@pytest.mark.parametrize(
    "text,expected",
    [
        # Datum + Zeit
        ("2025-09-01 23:59:32", datetime(2025, 9, 1, 23, 59, 32)),
        ("2025-01-02 9:07",     datetime(2025, 1, 2, 9, 7, 0)),
        ("  2025-12-31 00:00  ", datetime(2025, 12, 31, 0, 0, 0)),
        # Nur Zeit → benutzt heutiges Datum (hier eingefroren auf 2025-09-24)
        ("07:05",               datetime(2025, 9, 24, 7, 5, 0)),
        ("07:05:09",            datetime(2025, 9, 24, 7, 5, 9)),
        (" 7:5 ",               datetime(2025, 9, 24, 7, 5, 0)),
    ],
)
def test_parse_datetime_valid(text: str, expected: datetime):
    assert utils.parse_datetime_arg(text) == expected


@freeze_time("2025-09-24 13:00:00")
@pytest.mark.parametrize(
    "bad",
    [
        "2025/09/24 10:00",   # falsches Format
        "2025-13-01 10:00",   # ungültiger Monat
        "2025-02-30 10:00",   # ungültiger Tag
        "24:00",              # ungültige Stunde
        "10:60",              # ungültige Minute
        "10:00:60",           # ungültige Sekunde
        "foo",
        "",
        "2025-09-24",         # Datum ohne Zeit ist nicht erlaubt
    ],
)
def test_parse_datetime_invalid_raises(bad: str):
    with pytest.raises(argparse.ArgumentTypeError):
        _ = utils.parse_datetime_arg(bad)



@pytest.mark.parametrize(
    "text,expected",
    [
        ("0", 0),
        ("42", 42),
        ("   7   ", 7),   # Leerraum
        ("-3", -3),       # Vorzeichen
        ("003", 3),       # führende Nullen
        ("1_000", 1000),  # Unterstrich im String erlaubt
    ],
)
def test_safe_int_valid(text: str, expected: int):
    assert utils.safe_int(text) == expected


@pytest.mark.parametrize(
    "text,default,expected",
    [
        ("", 0, 0),                 # leer
        ("abc", 0, 0),              # nicht numerisch
        ("10.5", 0, 0),             # Float-String → ValueError
        (None, 0, 0),               # TypeError → default
        ("NaN", -1, -1),            # custom default
        (None, 9, 9),               # custom default mit None
    ],
)
def test_safe_int_invalid_uses_default(text: str, default: int, expected: int):
    assert utils.safe_int(text, default=default) == expected
