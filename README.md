# lms

A simple python script for interacting with the Logitech Media Server using the command line.

To install just place lms.py somewhere in your path and optionally create an lms symlink
``` shell
> ln -s /path/to/lms.py lms
```
There are basic commands

- play
- pause
- next
- prev
- volume

As well as commands for searching the music database, `search`, and adding tracks to the current playlist, `enqueue`.  See help for full details.
``` shell
> lms --help
```

Set `LMS_DEFAULT_HOST` and `LMS_DEFAULT_PLAYER` environment variables to simplify usage.

## Extras ##

See the file `lms_bash` for an example that uses fzf to search for tracks and enqueue them.
