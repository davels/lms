#!/usr/bin/env python3
#
# lms - Command-line client for the Lyrion Music Server
#
# Copyright (C) 2022-2026 David Shilvock
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# USAGE
# see lms --help
#

import sys, os
import urllib.request, urllib.error
import json
import argparse
from typing import NamedTuple

# ensure proper handling of utf8 tags
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# width of column 0 that holds the id of each output line from search commands
IDWIDTH = 8


class LMSError(Exception):
    pass

class LMSConnectionError(LMSError):
    pass

class LMSRequestError(LMSError):
    pass

class LMSArgumentError(LMSError):
    pass


def _safeint(strval):
    try:
        return int(strval)
    except (ValueError,TypeError):
        return -1

def _format_duration(time):
    minutes,seconds = divmod(int(time),60)
    return '{}:{:02}'.format(int(minutes),int(seconds))


class PlayerInfo(NamedTuple):
    name: str
    playerid: str
    model: str
    isplaying: bool


class Server(object):
    """Query the Lyrion Music Server."""
    def __init__(self, host="localhost", port="9000"):
        self.host = host
        self.port = port
        self._url = f'http://{self.host}:{self.port}/jsonrpc.js'

    def request(self, playerid="-", params=None):
        """Send a request to the server and return the results.
        params is a list of strings or a single string with params separated by spaces.
        """
        req = urllib.request.Request(self._url)
        req.add_header('Content-Type', 'application/json')
        if type(params) is str:
            params = params.split()
        cmd = [playerid, params]
        data = {'method': 'slim.request',
                'params': cmd}
        try:
            response = urllib.request.urlopen(req, bytes(json.dumps(data).encode('utf-8')))
            return json.loads(response.read().decode('utf-8'))['result']
        except urllib.error.URLError as err:
            raise LMSConnectionError(f'Could not connect to media server: {err}') from err
        except Exception as err:
            raise LMSConnectionError(f'Unkown server error: {err}') from err

    def enumerate_players(self):
        """Return a list of details for all players known to the server."""
        resp = self.request(params=f'players 0 999')
        if 'players_loop' not in resp:
            return []
        return [
            PlayerInfo(
                name=p["name"],
                playerid=p["playerid"],
                model=p["model"],
                isplaying=bool(p["isplaying"]),
            )
            for p in resp["players_loop"]
        ]

    def find_player(self, name):
        lname = name.lower()
        for p in self.enumerate_players():
            if p.name.lower() == lname:
                return Player(self, name, p.playerid)
        return None


class Player(object):
    """Send commands to a specific LMS player."""
    def __init__(self, server, name, playerid):
        self.server = server
        self.name = name
        self.playerid = playerid
        self.trim_id = False
        self.natural_indexing = True

    def __repr__(self):
        return f'LMS Player: {self.name} ({self.playerid})'

    def __bool__(self):
        return self.playerid is not None

    def player_request(self, command, key=None):
        try:
            res = self.server.request(self.playerid, command)
            if key:
                return res[key]
            return res
        except Exception as err:
            raise LMSRequestError(f'LMS player_request "{command}" failed: {err}') from err

    def poweron(self):
        """Turn the player on."""
        return self.player_request('power 1')

    def poweroff(self):
        """Turn the player off."""
        return self.player_request('power 0')

    def state(self):
        """Return current playing state: ("play", "pause", "stop")."""
        return self.player_request('mode ?', '_mode')

    def play(self):
        """Start playing the current item."""
        self.player_request('play')

    def stop(self):
        """Stop the player."""
        self.player_request('stop')

    def pause(self):
        """Pause the player. This does not unpause the player if already paused."""
        self.player_request('pause 1')

    def unpause(self):
        """Unpause the player."""
        self.player_request('pause 0')

    def toggle_pause(self):
        """Play/Pause Toggle."""
        self.player_request('pause')

    def next(self):
        """Play next item in playlist."""
        self.player_request('playlist index +1')

    def prev(self):
        """Play previous item in playlist."""
        self.player_request('playlist index -1')

    def vup(self, step=10):
        """Increase the volume."""
        return self.player_request(f'mixer volume +{step}')

    def vdown(self, step=10):
        """Decrease the volume."""
        return self.player_request(f'mixer volume -{step}')

    def volume(self, volume=None):
        """Print or set the volume."""
        if volume is None:
            print('Volume:', self.player_request('mixer volume ?','_volume'))
        else:
            if volume < 0: volume = 0
            elif volume > 100: volume = 100
            self.player_request(f'mixer volume {volume}')

    def track_artist(self):
        """Return the artist for the current playlist item."""
        return self.player_request('artist ?', '_artist')

    def track_album(self):
        """Return the album for the current playlist item."""
        return self.player_request('album ?', '_album')

    def track_title(self):
        """Return name of the track for the current playlist item."""
        return self.player_request('title ?', '_title')

    def playing(self, page=0, pagesize=9999):
        """Print tracks in the current playist."""
        res = self.player_request(f'status {page*pagesize} {pagesize} tags:a')
        if res['playlist_tracks'] == 0: return
        cur = _safeint(res.get('playlist_cur_index', -1))
        for track in res['playlist_loop']:
            tag = '*' if track["playlist index"]==cur else " "
            plindex = track["playlist index"]
            if self.natural_indexing: plindex+=1
            print(f'{plindex:6} {tag} {track["title"]} - {track["artist"]}')

    def setcurrent(self, plindex):
        """Set the current track in the current playlist."""
        if self.natural_indexing: plindex -= 1
        self.player_request(f'playlist index {plindex}')

    def _print_track(self, trackinfo):
        print('Title:   ', trackinfo['title'])
        print('Artist:  ', trackinfo.get('artist',''))
        print('Album:   ', trackinfo.get('album',''))
        print('Track:   ', trackinfo.get('tracknum',''))
        print('Year:    ', trackinfo.get('year',''))
        print('Genre:   ', trackinfo.get('genre',''))
        print('Duration:', _format_duration(trackinfo["duration"]))
        print('Encoding:', trackinfo['type'], trackinfo['bitrate'])
        print('Filesize:', '{:.1f}.Mb'.format(int(trackinfo['filesize'])/(1024*1024)))

    def playinginfo(self, plindex):
        """Print the details for the track with the specified index in the current playlist."""
        if self.natural_indexing: plindex -= 1
        res = self.player_request(f'status {plindex} 1 tags:a,d,f,g,i,l,o,q,r,t,y')
        if 'playlist_loop' not in res:
            return  # plindex provided is not valid
        self._print_track(res['playlist_loop'][0])

    def _build_search(self, term, param):
        if term == "-":
            # read term from stdin
            term = sys.stdin.readline().strip()
        if self.trim_id:
            term = term[:IDWIDTH].strip()
        else:
            term = term.strip() if term else ''
        if param:
            search = param + ":" + term
        elif term:
            search = 'search:' + term
        else:
            search = ''
        return search

    def search_artists(self, term, maxitems=9999):
        search = self._build_search(term, None)
        res = self.player_request(f'artists 0 {maxitems} {search}')
        if res['count'] == 0: return
        for artist in res['artists_loop']:
            print(f'{artist["id"]:{IDWIDTH}}  {artist["artist"]}')

    def search_albums(self, term, maxitems=9999):
        search = self._build_search(term, None)
        res = self.player_request(f'albums 0 {maxitems} tags:a,y,l {search}')
        if res['count'] == 0: return
        for album in res['albums_loop']:
            print(f'{album["id"]:{IDWIDTH}}  {album["album"]} ({album["year"]})  -  {album["artist"]}')

    def search_tracks(self, term, maxitems=9999):
        search = self._build_search(term, None)
        res = self.player_request(f'tracks 0 {maxitems} tags:a,l {search}')
        if res['count'] == 0: return
        for track in res['titles_loop']:
            print(f'{track["id"]:{IDWIDTH}}  {track["title"]}  -  {track["album"]}  -  {track["artist"]}')

    def match_artists(self, term, param, maxitems=9999):
        search = self._build_search(term, param)
        res = self.player_request(f'artists 0 {maxitems} {search}')
        if res['count'] == 0: return
        for artist in res['artists_loop']:
            print(f'{artist["id"]:{IDWIDTH}}  {artist["artist"]}')

    def match_albums(self, term, param, maxitems=9999):
        search = self._build_search(term, param)
        res = self.player_request(f'albums 0 {maxitems} tags:a,y,l {search}')
        if res['count'] == 0: return
        for album in res['albums_loop']:
            print(f'{album["id"]:{IDWIDTH}}  {album["album"]} ({album["year"]})  -  {album["artist"]}')

    def match_tracks(self, term, param, maxitems=9999):
        search = self._build_search(term, param)
        res = self.player_request(f'tracks 0 {maxitems} tags:a,l {search}')
        if res['count'] == 0: return
        for track in res['titles_loop']:
            print(f'{track["id"]:{IDWIDTH}}  {track["title"]}  -  {track["album"]}  -  {track["artist"]}')

    def _enqueue(self, itemtype, items, method):
        if method not in ['play','insert','add']:
            raise LMSArgumentError(f'{method} is not a valid enqueue method [play|insert|add]')
        if items == ['-']:
            # read items from stdin
            items = sys.stdin.readlines()
        items = [iid[0] for item in items if (iid:=str(item).split(maxsplit=1))]
        if not items:
            return  # do nothing if no items are provided
        # server uses 'load' for the play action
        if method=='play': method='load'
        # track is special and allows a comma separated list of ids
        if itemtype=='track': items = [','.join(items)]
        for itemid in items:
            self.player_request(f'playlistcontrol cmd:{method} {itemtype}_id:{itemid}')

    def enqueue_artists(self, items, method='add'):
        self._enqueue('artist', items, method)

    def enqueue_albums(self, items, method='add'):
        self._enqueue('album', items, method)

    def enqueue_tracks(self, items, method='add'):
        self._enqueue('track', items, method)

    def info_artists(self, artistid):
        res = self.player_request(f'artists 0 1 artist_id:{artistid}')
        artist = ''
        if 'artists_loop' in res:
            artist = res['artists_loop'][0].get('artist','')
        res = self.player_request(f'albums 0 9999 tags:a,l,y artist_id:{artistid}')
        if 'albums_loop' not in res:
            return
        albums = res['albums_loop']
        albums.sort(key=lambda t: t.get('year',-1))
        for album in albums:
            albumartist = album.get('artist','')
            if albumartist == artist:
                albumartist = ''
            else:
                albumartist = ' - ' + albumartist
            print(f'{album["album"]} ({album.get("year","")}){albumartist}')

    def info_albums(self, albumid):
        res = self.player_request(f'tracks 0 9999 tags:a,l,t,g,y,d album_id:{albumid}')
        if 'titles_loop' not in res:
            return
        tracks = res['titles_loop']
        tracks.sort(key=lambda t: _safeint(t.get('tracknum',-1)))
        print(f'{tracks[0]["album"]} ({tracks[0].get("year","")})')
        print(f'{tracks[0]["artist"]}')
        for track in tracks:
            dur = _format_duration(track["duration"])
            print(f'  {track.get("tracknum",""):>2}. {track["title"]}  ({dur})')

    def info_tracks(self, trackid):
        res = self.player_request(f'tracks 0 1 tags:a,d,f,g,i,l,o,q,r,t,y track_id:{trackid}')
        if 'titles_loop' not in res:
            return
        self._print_track(res['titles_loop'][0])


def print_status(player, natural_indexing=True):
    res = player.player_request('status')
    state = 'off'
    if res['power'] == 1:
        state = res['mode']  # play/pause/stop
    if 'time' in res and 'duration' in res:
        position = f'[{_format_duration(res["time"])}/{_format_duration(res["duration"])}]'
    else:
        position = '[-]'
    curtrack = ''
    if 'playlist_cur_index' in res:
        plindex = res["playlist_cur_index"]
        if natural_indexing:
            try:
                plindex = int(plindex) + 1
            except BaseException as err:
                raise LMSError(f'Invalid playlist index returned from status: {plindex}') from err
        curtrack = f'{plindex}/{res["playlist_tracks"]}'
        res = player.player_request(f'status {res["playlist_cur_index"]} 1 tags:a')
        if 'playlist_loop' in res:
            pl = res['playlist_loop']
            if pl:
                curtrack += f'.{pl[0]["title"]} - {pl[0]["artist"]}'
    print(f'{player.name} [{state}] {curtrack} {position}')


def command_setcurrent(player, args):
    if len(args.args) < 1:
        raise LMSArgumentError('Missing index for setcurrent')
    try:
        val = args.args[0]
        if args.trim_id:
            val = val[:IDWIDTH].strip()
        curr = int(val)
    except BaseException as err:
        raise LMSArgumentError(f'Invalid index for setcurrent: {args.args[0]}') from err
    player.setcurrent(curr)


def command_playinginfo(player, args):
    if len(args.args) < 1:
        raise LMSArgumentError('Missing index for playinginfo')
    try:
        item = int(args.args[0])
    except BaseException as err:
        raise LMSArgumentError(f'Invalid index for playinginfo: {args.args[0]}') from err
    player.playinginfo(item)


def command_search(player, args):
    if len(args.args) < 1:
        raise LMSArgumentError('no search type specified [artists|albums|tracks]')
    searchtype = args.args[0].lower()
    if searchtype not in ['artists','albums','tracks']:
        raise LMSArgumentError(f'{searchtype} is not a valid search type [artists|albums|tracks]')
    term = args.args[1] if len(args.args) > 1 else None
    method = getattr(player, 'search_'+searchtype)
    method(term, maxitems=args.maxitems)


def command_match(player, args):
    if len(args.args) < 1:
        raise LMSArgumentError('no match type specified [artists|albums|tracks]')
    searchtype = args.args[0].lower()
    if searchtype not in ['artists','albums','tracks']:
        raise LMSArgumentError(f'{searchtype} is not a valid match type [artists|albums|tracks]')
    term = args.args[1] if len(args.args) > 1 else None
    param = None
    if term:
        paramkeys = ('artist_id','album_id','track_id')
        parts = term.split(':',1)
        if len(parts) < 2:
            raise LMSArgumentError(f'Not a valid match expression: {term}')
        param = parts[0].lower()
        term = parts[1]
        if param not in paramkeys:
            raise LMSArgumentError(f'{param} is not a valid match parameter [{",".join(paramkeys)}]')
    method = getattr(player, 'match_'+searchtype)
    method(term, param=param, maxitems=args.maxitems)


def command_enqueue(player, args):
    if len(args.args) < 1:
        raise LMSArgumentError('no enqueue item type specified [artists|albums|tracks]')
    if len(args.args) < 2:
        raise LMSArgumentError('no item specified for enqueue')
    itype = args.args[0].lower()
    items = args.args[1:]
    if itype not in ['artists','albums','tracks']:
        raise LMSArgumentError(f'{itype} is not a valid item type [artists|albums|tracks]')
    if not items: return
    method = getattr(player, 'enqueue_'+itype)
    method(items, args.enqueue_method)


def command_info(player, args):
    if len(args.args) < 1:
        raise LMSArgumentError('no info type specified [artists|albums|tracks]')
    if len(args.args) < 2:
        raise LMSArgumentError('no item specified for info')
    itype = args.args[0].lower()
    itemid = args.args[1]
    if itype not in ['artists','albums','tracks']:
        raise LMSArgumentError(f'{itype} is not a valid item type [artist|album|track]')
    if args.trim_id:
        itemid = itemid[:IDWIDTH].strip()
    if not itemid: return
    method = getattr(player, 'info_'+itype)
    method(itemid)


def dispatch_command(player, args):
    playercmds = ['status','play','pause','stop','next','prev','poweron','poweroff','vup','vdown','volume']
    cmd = args.command.lower()
    if cmd not in playercmds:
        matches = [m for m in playercmds if m.startswith(cmd)]
        if len(matches) == 1:
            cmd = matches[0]
        elif len(matches) > 1:
            mstr = "[" + ", ".join(matches) + "]"
            raise LMSArgumentError(f"command prefix '{cmd}' is not unique. could be {mstr}")
    # special case player commands
    if cmd == 'status':
        print_status(player)
    elif cmd == 'pause':
        player.toggle_pause()
    elif cmd == 'volume':
        vol = None  # print the volume if nothing specified
        if len(args.args) > 0:
            try:
                vol = int(args.args[0])
            except ValueError:
                raise LMSArgumentError(f"volume must be a number '{args.args[0]}'")
        player.volume(vol)
    # standard player commands
    elif cmd in playercmds:
        method = getattr(player, cmd)
        method()
    # other functions
    elif cmd == 'playing':
        player.playing(0, args.maxitems)
    elif cmd == 'setcurrent':
        command_setcurrent(player, args)
    elif cmd == 'playinginfo':
        command_playinginfo(player, args)
    elif cmd == 'search':
        command_search(player, args)
    elif cmd == 'match':
        command_match(player, args)
    elif cmd == 'enqueue':
        command_enqueue(player, args)
    elif cmd == 'info':
        command_info(player, args)
    else:
        # invalid command
        raise LMSArgumentError(f"invalid command '{cmd}'")


def execute_command(player, args):
    # status header
    if args.status_header:
        print_status(player, not args.zero_indexing)
    if args.command is not None:
        dispatch_command(player, args)
    # exit player status
    if args.status:
        print_status(player, not args.zero_indexing)


def main():
    helpextra = '''
COMMAND:
  status
  play
  pause
  stop
  next
  prev
  poweron
  poweroff
  vup
  vdown
  volume [n]
  playing
  setcurrent <n>
  playinginfo <n>
  search [artists|albums|tracks] TERM
  match [artists|albums|tracks] ITEMS
  enqueue [artists|albums|tracks] ITEMS
  info [artists|albums|tracks] ITEM

  NOTE: ITEM for match, enqueue,  and info commands is the database id, as returned from search.

PARAMETER SEARCH
  The --param-search option changes the search method from text match to a parameter
  search. Permitted parameters are the following, each of which include a numberic id as
  returned from search.
    artist_id:<n>
    album_id:<n>
    track_id:<n>

ENVIRONMENT VARIABLES:
  LMS_DEFAULT_HOST    fallback value to use when HOST is not specified
  LMS_DEFAULT_PLAYER  fallback value to use when PLAYER is not specified
'''
    default_host = os.environ.get('LMS_DEFAULT_HOST')
    default_player = os.environ.get('LMS_DEFAULT_PLAYER')
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description='A simple script for interacting with the Logitech Media Server.',
                                     epilog=helpextra)
    parser.add_argument('-a','--host', required=not default_host, default=default_host,
                        help='LMS hostname')
    parser.add_argument('-p','--port', type=int, default=9000,
                        help='LMS port (default: %(default)s)')
    parser.add_argument('-n','--player', required=not default_player, default=default_player,
                        help='player name')
    parser.add_argument('-Z','--zero-indexing', action='store_true',
                        help='use zero indexing for playlist entries')
    parser.add_argument('-t','--trim-id', action='store_true',
                        help='item id is taken from the first field of args rather than the full line')
    parser.add_argument('-s','--status', action='store_true',
                        help='print a one line status for the player and the end of execution')
    parser.add_argument('-S','--status-header', action='store_true',
                        help='print a one line status for the player at the start of execution')
    parser.add_argument('-m','--search-max', type=int, default=9999, dest='maxitems',
                        help='maximum number of search results (default: %(default)s)')
    parser.add_argument('-e','--enqueue-method', default='add',
                        choices=['play','insert','add'],
                        help='method used to enqueue tracks for the enqueue command (default: add)')
    parser.add_argument('command', nargs='?', default=None,
                        help='player command')
    parser.add_argument('args', nargs='*', help='command arguments')

    if len(sys.argv) < 2:
        parser.print_help()
        parser.exit(0)
    args = parser.parse_args()

    server = Server(args.host, args.port)
    player = server.find_player(args.player)
    if not player:
        print("LMS player not found:", args.player, file=sys.stderr)
        sys.exit(1)
    if args.trim_id:
        player.trim_id = True
    if args.zero_indexing:
        player.natural_indexing = False
    try:
        execute_command(player, args)
    except LMSError as err:
        parser.error(str(err))


if __name__ == '__main__':
    main()


