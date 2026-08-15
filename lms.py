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

class LMSNoPlayerError(LMSError):
    pass


def _safeint(strval):
    try:
        return int(strval)
    except (ValueError,TypeError):
        return -1


class PlayerInfo(NamedTuple):
    name: str
    playerid: str
    model: str
    isplaying: bool


class Server:
    """Query the Lyrion Music Server."""
    def __init__(self, host="localhost", port="9000"):
        self.host = host
        self.port = port
        self._url = f"http://{self.host}:{self.port}/jsonrpc.js"

    def __repr__(self):
        return f"LMS Server: {self.host}:{self.port}"

    def request(self, playerid, *params):
        """Send a request to the server and return the results."""
        req = urllib.request.Request(self._url)
        req.add_header("Content-Type", "application/json")
        cmd = [playerid, params]
        data = {"method": "slim.request",
                "params": cmd}
        try:
            response = urllib.request.urlopen(req, bytes(json.dumps(data).encode("utf-8")))
            return json.loads(response.read().decode("utf-8"))["result"]
        except urllib.error.URLError as err:
            raise LMSConnectionError(f"Could not connect to media server: {err}") from err
        except Exception as err:
            raise LMSConnectionError(f"Unkown server error: {err}") from err

    def global_request(self, *params):
        """Send a server request not tied to a player."""
        return self.request(0, *params)  # 0 is the 'none' player

    def enumerate_players(self) -> list[PlayerInfo]:
        """Return a list of PlayerInfo details for all players known to the server."""
        resp = self.global_request("players", 0, 999)
        if "players_loop" not in resp:
            return []
        return [
            PlayerInfo(
                name=p["name"],
                playerid=p["playerid"],
                model=p["modelname"],
                isplaying=bool(p["isplaying"]),
            )
            for p in resp["players_loop"]
        ]

    def find_player(self, name):
        """Return the Player with the matching name."""
        lname = name.lower()
        for p in self.enumerate_players():
            if p.name.lower() == lname:
                return Player(self, p.playerid, name)
        return None


class Player:
    """Send commands for a specific LMS player."""
    def __init__(self, server: Server, playerid=None, name=""):
        self.server = server
        self.name = name
        self.playerid = playerid
        self.trim_id = False
        self.natural_indexing = True

    def __repr__(self):
        return f"LMS Player: {self.name} ({self.playerid})"

    def __bool__(self):
        return self.playerid is not None

    def player_request(self, command, *params):
        """Send a server request for this player and return the result dictionary."""
        if self.playerid is None:
            raise LMSNoPlayerError("LMS player not specified")
        try:
            return self.server.request(self.playerid, command, *params)
        except Exception as err:
            raise LMSRequestError(f'LMS player_request "{command}" failed: {err}') from err

    def player_request_result(self, reskey, command, *params):
        """Send a server request and return the reskey value from the returned dictionary."""
        res = self.player_request(command, *params)
        return res[reskey]

    def poweron(self):
        """Turn the player on."""
        self.player_request("power", 1)

    def poweroff(self):
        """Turn the player off."""
        self.player_request("power", 0)

    def state(self):
        """Return current playing state: ("play", "pause", "stop")."""
        return self.player_request_result("_mode", "mode", "?")

    def play(self):
        """Start playing the current item."""
        self.player_request("play")

    def stop(self):
        """Stop the player."""
        self.player_request("stop")

    def pause(self, state=None):
        """Pause the player.
        If state is not specified toggle pause, else pause is state is true and unpause if
        false."""
        if state is None:
            self.player_request("pause")
        else:
            self.player_request("pause", 1 if state else 0)

    def next(self):
        """Play next item in playlist."""
        self.player_request("playlist", "index", "+1")

    def prev(self):
        """Play previous item in playlist."""
        self.player_request("playlist", "index", "-1")

    def vup(self, step=10):
        """Increase the volume."""
        self.player_request("mixer", "volume", f"+{step}")

    def vdown(self, step=10):
        """Decrease the volume."""
        self.player_request("mixer", "volume", f"-{step}")

    def volume(self, volume=None):
        """Return or set the volume."""
        if volume is None:
            return self.player_request_result("_volume", "mixer", "volume", "?")
        else:
            if volume < 0: volume = 0
            elif volume > 100: volume = 100
            self.player_request("mixer", "volume", volume)

    def current_artist(self):
        """Return the artist for the current song in the 'now playing' playlist."""
        return self.player_request_result("_artist", "artist", "?")

    def current_album(self):
        """Return the album for the current song in the 'now playing' playlist."""
        return self.player_request_result("_album", "album","?")

    def current_title(self):
        """Return the title of the current song in the 'now playing' playlist."""
        return self.player_request_result("_title", "title", "?")

    def now_playing(self, page=0, pagesize=9999):
        """Return the tracks in the 'now playing' playist and the index of the current item.
        Uses 0-indexing for playist entries."""
        res = self.player_request("status", page*pagesize, pagesize, "tags:a")
        if res["playlist_tracks"] == 0:
            return ([],  0)
        cur = _safeint(res.get("playlist_cur_index", -1))
        return (res["playlist_loop"], cur)

    def set_current(self, plindex):
        """Set the current track in the 'now playing' playlist.
        plindex uses 0-indexing, or 1-indexing if natural_indexing is True."""
        if self.natural_indexing: plindex -= 1
        self.player_request("playlist", "index", plindex)

    def playing_info(self, plindex):
        """Print the details for the track with the specified index in the current playlist."""
        if self.natural_indexing: plindex -= 1
        # if plindex is invalid "playlist_loop" will be missing from results
        return self.player_request("status", plindex, 1,
                                   "tags:a,d,f,g,i,l,o,q,r,t,y").get("playlist_loop")[0]

    def _build_search(self, term: str):
        term = term.strip()
        return "search:" + term if term else ""

    def _build_match(self, idtag: str, term: str):
        if self.trim_id:
            term = term[:IDWIDTH].strip()
        else:
            term = term.strip()
        return idtag + ":" + term if term else ""

    def search_artists(self, term: str, maxitems: int = 9999):
        search = self._build_search(term)
        res = self.player_request("artists", 0, maxitems, search)
        if res["count"] == 0: return
        for artist in res["artists_loop"]:
            print(f'{artist["id"]:{IDWIDTH}}  {artist["artist"]}')

    def search_albums(self, term: str, maxitems: int = 9999):
        search = self._build_search(term)
        res = self.player_request("albums", 0, maxitems, "tags:a,y,l", search)
        if res["count"] == 0: return
        for album in res["albums_loop"]:
            print(f'{album["id"]:{IDWIDTH}}  {album["album"]} ({album["year"]})  -  {album["artist"]}')

    def search_tracks(self, term: str, maxitems: int = 9999):
        search = self._build_search(term)
        res = self.player_request("tracks", 0, maxitems, "tags:a,l", search)
        if res["count"] == 0: return
        for track in res["titles_loop"]:
            print(f'{track["id"]:{IDWIDTH}}  {track["title"]}  -  {track["album"]}  -  {track["artist"]}')

    def match_artists(self, idtag: str, term: str, maxitems: int = 9999, tags: str = ""):
        search = self._build_match(idtag, term)
        if tags: tags = "tags:" + tags
        res = self.player_request("artists", 0, maxitems, tags, search)
        return res["artists_loop"] if res["count"] != 0 else None

    def match_albums(self, idtag: str, term: str, maxitems: int = 9999, tags: str = "a,y,l"):
        search = self._build_match(idtag, term)
        if tags: tags = "tags:" + tags
        res = self.player_request("albums", 0, maxitems, tags, search)
        return res["albums_loop"] if res["count"] != 0 else None

    def match_tracks(self, idtag: str, term: str, maxitems: int = 9999, tags: str = "a,l"):
        search = self._build_match(idtag, term)
        if tags: tags = "tags:" + tags
        res = self.player_request("tracks", 0, maxitems, tags, search)
        return res["titles_loop"] if res["count"] != 0 else None

    def _enqueue(self, itemtype : str, items: list[str], method: str):
        if method not in ["play","insert","add"]:
            raise LMSArgumentError(f"{method} is not a valid enqueue method [play|insert|add]")
        if items == ['-']:
            # read items from stdin
            items = sys.stdin.readlines()
        items = [iid[0] for item in items if (iid:=str(item).split(maxsplit=1))]
        if not items:
            return  # do nothing if no items are provided
        # server uses 'load' for the play action
        if method=="play": method="load"
        # track is special and allows a comma separated list of ids
        if itemtype=="track": items = [",".join(items)]
        for itemid in items:
            self.player_request("playlistcontrol", f"cmd:{method}", f"{itemtype}_id:{itemid}")

    def enqueue_artists(self, items: list[str], method="add"):
        self._enqueue("artist", items, method)

    def enqueue_albums(self, items: list[str], method="add"):
        self._enqueue("album", items, method)

    def enqueue_tracks(self, items: list[str], method="add"):
        self._enqueue("track", items, method)


### Helper functions


def format_duration(time):
    minutes,seconds = divmod(int(time),60)
    return "{}:{:02}".format(int(minutes),int(seconds))


def print_status(player: Player, natural_indexing=True):
    res = player.player_request("status")
    state = "off"
    if res["power"] == 1:
        state = res["mode"]  # play/pause/stop
    if "time" in res and "duration" in res:
        position = f'[{format_duration(res["time"])}/{format_duration(res["duration"])}]'
    else:
        position = "[-]"
    curtrack = ""
    if "playlist_cur_index" in res:
        plindex = res["playlist_cur_index"]
        if natural_indexing:
            try:
                plindex = int(plindex) + 1
            except BaseException as err:
                raise LMSError(f"Invalid playlist index returned from status: {plindex}") from err
        curtrack = f'{plindex}/{res["playlist_tracks"]}'
        res = player.player_request("status", f'{res["playlist_cur_index"]}', 1, "tags:a")
        if "playlist_loop" in res:
            pl = res["playlist_loop"]
            if pl:
                curtrack += f'.{pl[0]["title"]} - {pl[0]["artist"]}'
    print(f"{player.name} [{state}] {curtrack} {position}")


def print_track(trackinfo):
    print("Title:   ", trackinfo["title"])
    print("Artist:  ", trackinfo.get("artist",""))
    print("Album:   ", trackinfo.get("album",""))
    print("Track:   ", trackinfo.get("tracknum",""))
    print("Year:    ", trackinfo.get("year",""))
    print("Genre:   ", trackinfo.get("genre",""))
    print("Duration:", format_duration(trackinfo["duration"]))
    print("Encoding:", trackinfo["type"], trackinfo["bitrate"])
    print("Filesize:", "{:.1f}.Mb".format(int(trackinfo["filesize"])/(1024*1024)))


### Command Functions

def command_players(server: Server, args):
    players = server.enumerate_players()
    if args.verbose:
        maxname = max(len(p.name) for p in players)
        for p in players:
            print(f'{"*" if p.isplaying else " "} {p.name:{maxname}}  {p.model}')
    else:
        for p in players:
            print(p.name)


def command_volume(player: Player, args):
    if len(args.args) == 0:
        print("Volume:", player.volume())
    else:
        try:
            vol = int(args.args[0])
        except ValueError:
            raise LMSArgumentError(f'volume must be a number "{args.args[0]}"')
        player.volume(vol)


def command_playing(player: Player, args):
    tracks,cur = player.now_playing(0, args.maxitems)
    for track in tracks:
        tag = "*" if track["playlist index"]==cur else " "
        plindex = track["playlist index"]
        if player.natural_indexing: plindex+=1
        print(f'{plindex:6} {tag} {track["title"]} - {track["artist"]}')


def command_setcurrent(player: Player, args):  # plindex
    if len(args.args) < 1:
        raise LMSArgumentError("Missing index for setcurrent")
    try:
        val = args.args[0]
        if args.trim_id:
            val = val[:IDWIDTH].strip()
        curr = int(val)
    except BaseException as err:
        raise LMSArgumentError(f"Invalid index for setcurrent: {args.args[0]}") from err
    player.set_current(curr)


def command_playinginfo(player: Player, args):  # plindex
    if len(args.args) < 1:
        raise LMSArgumentError("Missing index for playinginfo")
    try:
        item = int(args.args[0])
    except BaseException as err:
        raise LMSArgumentError(f"Invalid index for playinginfo: {args.args[0]}") from err
    info = player.playing_info(item)
    if info:
        print_track(info)


def command_search(player: Player, args):  # typename search_term
    if len(args.args) < 1:
        raise LMSArgumentError("no search type specified [artists|albums|tracks]")
    searchtype = args.args[0].lower()
    if searchtype not in ["artists","albums","tracks"]:
        raise LMSArgumentError(f"{searchtype} is not a valid search type [artists|albums|tracks]")
    term = args.args[1] if len(args.args) > 1 else None
    method = getattr(player, "search_"+searchtype)
    method(term, maxitems=args.maxitems)


def command_match(player: Player, args):  # typename tagged_param
    if len(args.args) < 1:
        raise LMSArgumentError("no match type specified [artists|albums|tracks]")
    searchtype = args.args[0].lower()
    if searchtype not in ["artists","albums","tracks"]:
        raise LMSArgumentError(f"{searchtype} is not a valid match type [artists|albums|tracks]")
    term = args.args[1] if len(args.args) > 1 else None
    if not term: return
    idtag = None
    tagkeys = ("artist_id","album_id","track_id")
    parts = term.split(":",1)
    if len(parts) < 2:
        raise LMSArgumentError(f"Not a valid match expression: {term}")
    idtag = parts[0].lower()
    term = parts[1]
    if idtag not in tagkeys:
        raise LMSArgumentError(f'{idtag} is not a valid match idtageter [{",".join(tagkeys)}]')
    method = getattr(player, "match_"+searchtype)
    res = method(idtag, term, maxitems=args.maxitems)
    if not res: return
    match searchtype:
        case "artists":
            for artist in res:
                print(f'{artist["id"]:{IDWIDTH}}  {artist["artist"]}')
        case "albums":
            for album in res:
                print(f'{album["id"]:{IDWIDTH}}  {album["album"]} ({album["year"]})  -  {album["artist"]}')
        case "tracks":
            for track in res:
                print(f'{track["id"]:{IDWIDTH}}  {track["title"]}  -  {track["album"]}  -  {track["artist"]}')


def command_enqueue(player: Player, args):  # typename ids
    if len(args.args) < 1:
        raise LMSArgumentError("no enqueue item type specified [artists|albums|tracks]")
    if len(args.args) < 2:
        raise LMSArgumentError("no item specified for enqueue")
    itype = args.args[0].lower()
    items = args.args[1:]
    if itype not in ["artists","albums","tracks"]:
        raise LMSArgumentError(f"{itype} is not a valid item type [artists|albums|tracks]")
    if not items: return
    method = getattr(player, "enqueue_"+itype)
    method(items, args.enqueue_method)


def command_info(player: Player, args):  # typename ids
    if len(args.args) < 1:
        raise LMSArgumentError("no info type specified [artists|albums|tracks]")
    if len(args.args) < 2:
        raise LMSArgumentError("no item specified for info")
    infotype = args.args[0].lower()
    itemid = args.args[1]
    if infotype not in ["artists","albums","tracks"]:
        raise LMSArgumentError(f"{infotype} is not a valid item type [artist|album|track]")
    if args.trim_id:
        itemid = itemid[:IDWIDTH].strip()
    if not itemid: return
    match infotype:
        case "artists":
            res = player.match_artists("artist_id", itemid, 1)
            artist = res[0].get("artist","") if res else ""
            res = player.match_albums("artist_id", itemid)
            if not res: return
            res.sort(key=lambda t: _safeint(t.get("year",-1)))
            for album in res:
                albumartist = album.get("artist","")
                if albumartist == artist:
                    albumartist = ""
                else:
                    albumartist = " - " + albumartist
                print(f'{album["album"]} ({album.get("year","")}){albumartist}')
        case "albums":
            res = player.match_tracks("album_id", itemid, tags = "a,l,t,g,y,d")
            if not res: return
            res.sort(key=lambda t: _safeint(t.get("tracknum",-1)))
            for track in res:
                dur = format_duration(track["duration"])
                print(f'  {track.get("tracknum",""):>2}. {track["title"]}  ({dur})')
        case "tracks":
            res = player.match_tracks("track_id", itemid, tags="a,d,f,g,i,l,o,q,r,t,y")
            if not res: return
            for track in res:
                print_track(track)


def dispatch_command(player: Player, args):
    # no arg player commands
    simplecmds = ["play","pause","stop","next","prev","poweron","poweroff","vup","vdown"]
    # complex commands
    othercmds = ["players","status","volume","playing","setcurrent","playinginfo","search","match","enqueue","info"]

    allcmds = simplecmds + othercmds
    cmd = args.command.lower()
    if cmd not in allcmds:
        matches = [m for m in allcmds if m.startswith(cmd)]
        if len(matches) == 1:
            cmd = matches[0]
        elif len(matches) > 1:
            mstr = "[" + ", ".join(matches) + "]"
            raise LMSArgumentError(f'command prefix "{cmd}" is not unique. could be {mstr}')
    # server commands
    if cmd == "players":
        command_players(player.server, args)
    # simple player commands
    elif cmd in simplecmds:
        method = getattr(player, cmd)
        method()
    # other player commands
    elif cmd == "status":
        print_status(player)
    elif cmd == "volume":
        command_volume(player, args)
    elif cmd == "playing":
        command_playing(player, args)
    elif cmd == "setcurrent":
        command_setcurrent(player, args)
    elif cmd == "playinginfo":
        command_playinginfo(player, args)
    elif cmd == "search":
        command_search(player, args)
    elif cmd == "match":
        command_match(player, args)
    elif cmd == "enqueue":
        command_enqueue(player, args)
    elif cmd == "info":
        command_info(player, args)
    else:
        # invalid command
        raise LMSArgumentError(f"invalid command '{cmd}'")


def execute_command(player: Player, args):
    # status header
    if args.status_header:
        print_status(player, not args.zero_indexing)
    if args.command is not None:
        dispatch_command(player, args)
    # exit player status
    if args.status:
        print_status(player, not args.zero_indexing)


def main():
    helpextra = """
COMMAND:
  players
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
  search [artists|albums|tracks] <TERM>
  match [artists|albums|tracks] <TAGGED_PARAMETER>
  enqueue [artists|albums|tracks] <ITEM_IDS>
  info [artists|albums|tracks] <ITEM_IDS>

ITEM_IDS
  The database ids, as returned from SEARCH and MATCH.

TAGGED_PARAMETER
  A named parameter followed by a colon and 1 or more ITEM_ID values separated by
  commas. Examples:
    artist_id:6699
    album_id:2245,3659
    track_id:1944

ENVIRONMENT VARIABLES:
  LMS_DEFAULT_HOST    fallback value to use when HOST is not specified
  LMS_DEFAULT_PLAYER  fallback value to use when PLAYER is not specified
"""
    default_host = os.environ.get("LMS_DEFAULT_HOST")
    default_player = os.environ.get("LMS_DEFAULT_PLAYER")
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description="A simple script to control a Lyrion Music Server.",
                                     epilog=helpextra)
    parser.add_argument("-a","--host", required=not default_host, default=default_host,
                        help="LMS hostname")
    parser.add_argument("-p","--port", type=int, default=9000,
                        help="LMS port (default: %(default)s)")
    parser.add_argument("-n","--player", default=default_player,
                        help="player name")
    parser.add_argument("-Z","--zero-indexing", action="store_true",
                        help="use zero indexing for playlist entries")
    parser.add_argument("-t","--trim-id", action="store_true",
                        help="item id is taken from the first field of args rather than the full line")
    parser.add_argument("-s","--status", action="store_true",
                        help="print a one line status for the player and the end of execution")
    parser.add_argument("-S","--status-header", action="store_true",
                        help="print a one line status for the player at the start of execution")
    parser.add_argument("-m","--search-max", type=int, default=9999, dest="maxitems",
                        help="maximum number of search results (default: %(default)s)")
    parser.add_argument("-e","--enqueue-method", default="add",
                        choices=["play","insert","add"],
                        help="method used to enqueue tracks for the enqueue command (default: add)")
    parser.add_argument("-v","--verbose", action="store_true",
                        help="include extra information in output")
    parser.add_argument("command", nargs="?", default=None,
                        help="command")
    parser.add_argument("args", nargs="*", help="command arguments")

    if len(sys.argv) < 2:
        parser.print_help()
        parser.exit(0)
    args = parser.parse_args()

    server = Server(args.host, args.port)
    if args.player:
        player = server.find_player(args.player)
        if not player:
            print("LMS player not found:", args.player, file=sys.stderr)
            sys.exit(1)
    else:
        player = Player(server)  # unspecified player
    if args.trim_id:
        player.trim_id = True
    if args.zero_indexing:
        player.natural_indexing = False
    try:
        execute_command(player, args)
    except LMSError as err:
        parser.error(str(err))


if __name__ == "__main__":
    main()
