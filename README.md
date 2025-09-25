# Radio Paradise Stream Recording and Playlist Tracking

These are my personal tools for recording [Radio Paradise][1] audio streams and
tracking their playlists. I originally built them for myself, but if they’re
useful to you, feel free to use them.

The recording tool should also work with other Shoutcast streams, but the
playlist tracking is Radio Paradise–specific.

If you enjoy Radio Paradise as much as I do, please consider donating to
support them. They truly deserve it.

## Installation

Build the wheel package with `uv`:

```console
$ uv sync
$ uv build
```

Afterwards, the `dist` directory will contain a `.whl` file that you can
install with `pip`.

> **Note:** Python packaging and installation can be a mess, depending on your
> system. Please avoid polluting your system’s Python installation with `pip`.
> Instead, either use the provided Docker container or run it directly with
> `uv run ...`.

Copy the sample configuration file `radioparadise.toml.sample` to
`radioparadise.toml` (or rename it) and adjust the settings as needed.

### Using the Docker container

*(to be documented)*

## CLI: `rp-record`

The recorder requires a `[recording]` section and at least one `[[streams]]`
entry in your configuration file.

- `streams.url`: Shoutcast stream URL
- `streams.type`: appropriate file extension, e.g. `m4a` (AAC), `mp3` (MP3)
  or `flac` (FLAC)
- `streams.cuesheet`: set to `true` to generate a cuesheet
- `streams.tracklist`: set to `true` to generate a plain text track list with
  time offsets
- `recording.output`: output directory path
- `recording.cuesheet`: default value for `streams.cuesheet`
- `recording.tracklist`: default value for `streams.tracklist`

Example: record one hour of the main RP mix:

```console
$ uv run rp-record --config rp.toml --duration 3600
```

## CLI: `rp-track`

If you only care about the playlist and not the audio, you can just track
the played titles via the RP API and save bandwidth.

`rp-track` writes the playlists into a SQLite3 database.

Required configuration entries:

- `tracking.url`: Radio Paradise API URL
- `tracking.contact`: contact string used in API requests (don’t use your
  email address unless you’re comfortable exposing it)
- `tracking.database`: SQLite database path

Example: track all configured channels until interrupted with `Ctrl-C`:

```console
$ uv run rp-track --config rp.toml
```

There’s no dedicated CLI for querying the database. Use your preferred
SQLite3 browser and inspect the tables or views.

Example SQL query:

```sql
SELECT
  pl.time,
  ch.name,
  tr.artist,
  tr.title,
  tr.album,
  tr.year,
  tr.cover
FROM playlists AS pl
JOIN channels AS ch ON ch.channel = pl.channel
JOIN tracks   AS tr ON tr.track   = pl.track
ORDER BY pl.time;
```

## Cuesheets

For audio recordings, you can optionally generate a cuesheet or track list.
Note that timestamps are only as accurate as the stream metadata — not exact
audio positions. Improving this would require decoding and analyzing the audio
data itself.

One peculiarity: the cuesheet standard supports at most 99 tracks. That’s fine
for CD-like media, but long stream recordings can easily exceed this limit.
Behavior depends on the playback program. As a workaround, this tool writes
multiple cuesheets within the same file, each capped at 99 tracks but all
pointing to the same audio file.

## License

Released under the 2-clause BSD license.

[1]: https://radioparadise.com/
