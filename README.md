# Shoutcast/Radio Paradise stream recording

These are my tools for tracking [Radio Paradise][1] playlist and recording
audio streams. I created them for my own purposes, but if they are useful to
you, feel free to use them. The recording tool should work with other
Shoutcast streams, but the rest is RP-specific.

If you like Radio Paradise as much as I do, consider making a donation to
them, they deserve it ;-)

## Installing

Build the wheel package file with `pipenv`:

```console
$ cd rp-recorder
$ pipenv install
$ pipenv run python setup.py bdist_wheel
```

Afterwards, inside of folder `dist` you will find the `.whl` file which you
can install with `pip`.

## CLI `rp-record`

Example YAML configuration file `rp.yaml`:

```yaml
- name: "RP Main Mix"
  url: "https://stream.radioparadise.com/aac-320"
  type: "mp4"
  cuesheet: true
  tracklist: false
```

Record one hour of RP main mix into folder `record`:

```console
$ rp-record --config rp.yaml --duration 3600 --output record
```

## CLI `rp-track`

If you are not interested in the music, but only in the played tracks, you
don't need to waste bandwidth on the audio stream. Just track the played
titles via their API.

With `rp-track` only the playlists of Radio Paradise are tracked and written
to a SQLite3 database.

```console
$ rp-track
```

There is also no frontend for the recorded tracks, you have to access the
database directly and query it with SQL. For example, to view the titles
played on all channels of RP, use this SQL statement:

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
JOIN channels AS ch ON ch.channel=pl.channel
JOIN tracks AS tr ON tr.track=pl.track
ORDER BY pl.time
```

## Cuesheet

For audio recordings, you can have a cuesheet or track list generated. The
time stamps are not really exact, because they refer to the stream, not to the
audio playback. To improve this it would be necessary to decode and evaluate
the audio data format.

The cuesheet has another peculiarity: the cuesheet standard allows only
a maximum of 99 tracks. This is quite sufficient for audio media such as CDs,
but for a stream recording you reach the limit quite easily. I am not aware of
how playback programs react when more than 99 tracks are included. A possible
alternative is to have several cuesheets in the same file, each with a maximum
of 99 tracks, but all pointing to the same audio file. Currently I have
implemented it exactly like this.

## License

Released under 2-clause BSD license.


[1]: https://radioparadise.com/
