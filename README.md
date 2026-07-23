# lms

![License](https://img.shields.io/github/license/davels/lms)
![Python](https://img.shields.io/badge/python-3-blue)
![CI](https://github.com/davels/lms/actions/workflows/ci.yml/badge.svg)

A simple python script for interacting with the Lyrion Music Server using the command line.

## Setup

To install just place lms.py somewhere in your path and create a symlink
``` shell
> ln -s /path/to/lms.py lms
```

Specify the server and player using environment variables:

``` shell
export LMS_DEFAULT_HOST=server_host
export LMS_DEFAULT_PLAYER=player_name
```

Or via the command line:

``` shell
lms -a server_host -n player_name status
```

## Usage

There are basic commands

- status
- play
- pause
- next
- prev
- volume

Commands for searching the music database `search [artists|albums|tracks]`
``` shell
> lms search artists de
   5544  Deftones
   5543  Def Leppard
```

And commands for adding tracks to the current playlist, based on ids returned from search, `enqueue`
``` shell
> lms enqueue artists 5544
```

See help for full details.
``` shell
> lms --help
```

## Requirements

- A running [Lyrion Music Server](https://lyrion.org/) instance (default: `localhost:9000`)
- [Python 3](https://www.python.org)

## Extras

### lms_bash

An example that uses [fzf](https://github.com/junegunn/fzf) to search for tracks and enqueue them.
