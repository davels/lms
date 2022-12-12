#! /bin/env python
#
# lms - a simple script to interact with the Logitech Media Server
#
# USAGE
# see lms --help
#

import sys
import urllib.request, urllib.parse, urllib.error
import json
import argparse


# width of column 0 that holds the id of each output line from search commands
IDWIDTH = 8

def _safeint(strval):
    try:
        return int(strval)
    except:
        return -1

def _format_duration(time):
    minutes,seconds = divmod(int(time),60)
    return '{}:{:02}'.format(int(minutes),int(seconds))
        
    
class ConnectionError(Exception):
    pass

class ArgumentError(Exception):
    pass

class Player(object):
    def __init__(self, name, host="localhost", port="9000"):
        self.host = host
        self.port = port
        self.name = name
        self.natural_indexing = True
        self._mac = None
        self._url = f'http://{self.host}:{self.port}/jsonrpc.js'
        self.find_player()
        
    def __repr__(self):
        return f'LMS Player: {self.name} ({self._mac})'
    
    def __bool__(self):
        return self._mac is not None

    def find_player(self):
        try:
            lname = self.name.lower()
            count = self.request(params='player count ?')['_count']
            for pinfo in self.request(params=f'players 0 {count}')['players_loop']:
                if pinfo['name'].lower() == lname:
                    self._mac = pinfo['playerid']
                    return True
        except ConnectionError as err:
            print("LMS error locating player:", err, file=sys.stderr)
        print("LMS player not found:", self.name, file=sys.stderr)
        return False
                
    def request(self, player="-", params=None):
        req = urllib.request.Request(self._url)
        req.add_header('Content-Type', 'application/json')

        if type(params) == str:
            params = params.split()            
        cmd = [player, params]
        data = {'method': 'slim.request',
                'params': cmd}
        try:
            response = urllib.request.urlopen(req, bytes(json.dumps(data).encode('utf-8')))
            return json.loads(response.read().decode('utf-8'))['result']
        except urllib.error.URLError as err:
            raise ConnectionError("Could not connect to server.", err)
        except Exception as err:
            raise ConnectionError("Unkown server error", err)

    def player_request(self, command, key=None):
        try:
            res = self.request(self._mac, command)
            if key:
                return res[key]
            return res
        except BaseException as err:
            print(f'LMS player_request "{command}" failed: {err}', file=sys.stderr)

    def poweron(self):
        return self.player_request('power 1')

    def poweroff(self):
        return self.player_request('power 0')
     
    def state(self):
        """Return current player state: ("play", "pause", "stop")"""
        return self.player_request('mode ?', '_mode')

    def play(self):
        """Start playing the current item"""
        self.player_request('play')

    def stop(self):
        """Stop the player"""
        self.player_request('stop')

    def pause(self):
        """Pause the player. This does not unpause the player if already paused."""
        self.player_request('pause 1')

    def unpause(self):
        """Unpause the player."""
        self.player_request('pause 0')

    def toggle_pause(self):
        """Play/Pause Toggle"""
        self.player_request('pause')

    def next(self):
        """Play next item in playlist"""
        self.player_request('playlist index +1')

    def prev(self):
        """Play previous item in playlist"""
        self.player_request('playlist index -1')

    def vup(self, step=10):
        """Increase the volume"""
        return self.player_request(f'mixer volume +{step}')

    def vdown(self, step=10):
        """Decrease the volume"""
        return self.player_request(f'mixer volume -{step}')

    def volume(self, volume=None):
        """Print or set the volume"""
        if not volume:
            print('Volume:', self.player_request('mixer volume ?','_volume'))
        else:
            if volume < 0: volume = 0
            elif volume > 100: volume = 100
            self.player_request('mixer volume {volume}')
    
    def track_artist(self):
        """Return the artist for the current playlist item"""
        return self.player_request('artist ?', '_artist')

    def track_album(self):
        """Return the album for the current playlist item"""
        return self.player_request('album ?', '_album')
    
    def track_title(self):
        """Return name of the track for the current playlist item"""
        return self.player_request('title ?', '_title')

    def playing(self, maxitems=None):
        """Print all tracks current playist"""
        res = self.player_request('status 0 99999 tags:a')
        cur = _safeint(res['playlist_cur_index'])
        if 'playlist_loop' in res:
            for track in res['playlist_loop']:
                tag = '*' if track["playlist index"]==cur else " "
                plindex = track["playlist index"]
                if self.natural_indexing: plindex+=1
                print(f'{plindex:6} {tag} {track["title"]} - {track["artist"]}')

    def setcurrent(self, plindex):
        """Set the current track in the current playlist"""
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
    
    def playinglistinfo(self, plindex):
        """Print the details for the item with the specified index in the current playlist"""
        if self.natural_indexing: plindex -= 1
        res = self.player_request(f'status {plindex} 1 tags:a,d,f,g,i,l,o,q,r,t,y')
        if 'playlist_loop' not in res:
            return  # plindex provided is not valid
        self._print_track(res['playlist_loop'][0])
        
    def search_artists(self, term, isfilter=False, maxitems=None):
        if isfilter:
            search = term
        else:
            search = 'search:' + term if term else ''        
        res = self.player_request(f'artists 0 {maxitems} {search}')
        if res['count'] == 0: return
        for artist in res['artists_loop']:
            print(f'{artist["id"]:{IDWIDTH}}  {artist["artist"]}')

    def search_albums(self, term, isfilter=False, maxitems=None):
        if isfilter:
            search = term
        else:
            search = 'search:' + term if term else ''
        res = self.player_request(f'albums 0 {maxitems} tags:a,y,l {search}')
        if res['count'] == 0: return
        for album in res['albums_loop']:
            print(f'{album["id"]:{IDWIDTH}}  {album["album"]} ({album["year"]})  -  {album["artist"]}')

    def search_tracks(self, term, isfilter=False, maxitems=None):
        if isfilter:
            search = term
        else:        
            search = 'search:' + term if term else ''
        res = self.player_request(f'tracks 0 {maxitems} tags:a,l {search}')
        if res['count'] == 0: return
        for track in res['titles_loop']:
            print(f'{track["id"]:{IDWIDTH}}  {track["title"]}  -  {track["album"]}  -  {track["artist"]}')

    def _enqueue(self, itemtype, items, method):
        if method not in ['load','insert','add']:
            raise ArgumentError(f'{method} is not a valid enqueue method [load|insert|add]')
        items = ','.join(str(itemid) for itemid in items)
        if items == '-':
            # read items from stdin
            items = ','.join(line.strip() for line in sys.stdin.readlines())
        if not items:
            return # do nothing if not items are provided
        self.player_request(f'playlistcontrol cmd:{method} {itemtype}_id:{items}')
        
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
        if not 'albums_loop' in res:
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
        if not 'titles_loop' in res:
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
        if not 'titles_loop' in res:
            return
        self._print_track(res['titles_loop'][0])
        
def print_status(player, natural_indexing=True):
    res = player.player_request('status')
    state = 'off'
    if res['power'] == 1:
        state = res['mode']  #play/pause/stop
    position = f'[{_format_duration(res["time"])}/{_format_duration(res["duration"])}]'
    curtrack = ''
    if 'playlist_cur_index' in res:
        plindex = res["playlist_cur_index"]
        if natural_indexing:
            try:
                plindex  = int(plindex) + 1
            except:
                pass
        curtrack = f'{plindex}/{res["playlist_tracks"]}'
        res = player.player_request(f'status {res["playlist_cur_index"]} 1 tags:a')
        if 'playlist_loop' in res:
            pl = res['playlist_loop']
            if pl:
                curtrack += f'.{pl[0]["title"]} - {pl[0]["artist"]}'
    print(f'{player.name} [{state}] {curtrack} {position}')

def dispatch_command(player, args):
    playercmds = ['play','pause','stop','next','prev','poweron','poweroff','vup','vdown','volume']
    cmd = args.command.lower()
    if cmd not in playercmds:
        # look for a unique command prefix match
        cmdmatch = None
        for c in playercmds:
            if c.startswith(cmd):
                if cmdmatch:
                    cmdmatch = None  # not a unique match
                    break
                cmdmatch = c
        if cmdmatch: cmd = cmdmatch
    # basic commands
    if cmd == 'pause':  # special case
        player.toggle_pause()
    elif cmd in playercmds:
        method = getattr(player, cmd)
        method()
        
    # playing list
    elif cmd == 'playing':
        player.playing(args.maxitems)
    elif cmd == 'setcurrent':
        try:
            curr = int(args.args[0])
        except:
            return  # do nothing if a new current item isn't specified
        player.setcurrent(curr)
    elif cmd == 'playinglistinfo':
        try:
            item = int(args.args[0])
        except:
            return  # do nothing if a playlist item isn't specified
        player.playinglistinfo(item)

    # search
    elif cmd == 'search':
        if len(args.args) < 1:
            raise ArgumentError('no search type specified [artists|albums|tracks]')
        searchtype = args.args[0].lower()
        if searchtype not in ['artists','albums','tracks']:
            raise ArgumentError(f'{searchtype} is not a valid search type [artists|albums|tracks]')
        term = args.args[1] if len(args.args) > 1 else None
        isfilter = False
        if term and args.filter_term:
            parts = term.split(':',1)
            if len(parts) < 2:
                raise ArgumentError('Not a valid filter expression')
            key = parts[0].lower()
            val = parts[1]
            keymap = {'artists':'artist_id','albums':'album_id','tracks':'track_id'}
            key = keymap.get(key,key)
            if key not in keymap.values():
                raise ArgumentError(f'{key} is not a valid filter type [{",".join(keymap.values())}]')
            if args.trim_id:
                val = val[:IDWIDTH].strip()
            term = key + ':' + val
            isfilter = True            
        method = getattr(player, 'search_'+searchtype)
        method(term, isfilter=isfilter, maxitems=args.maxitems)

    # enqueue
    elif cmd == 'enqueue':
        if len(args.args) < 1:
            raise ArgumentError('no enqueue item type specified [artists|albums|tracks]')
        itype = args.args[0].lower()
        items = args.args[1:]
        if itype not in ['artists','albums','tracks']:
            raise ArgumentError(f'{itype} is not a valid item type [artists|albums|tracks]')
        if not items: return
        method = getattr(player, 'enqueue_'+itype)
        method(items, args.enqueue_method)

    # info
    elif cmd == 'info':
        if len(args.args) < 1:
            raise ArgumentError('no info type specified [artists|albums|tracks]')
        itype = args.args[0].lower()
        if len(args.args) < 2: return
        itemid = args.args[1]
        if args.trim_id:
            itemid = itemid[:IDWIDTH].strip()
        if itype not in ['artists','albums','tracks']:
            raise ArgumentError(f'{itype} is not a valid item type [artist|album|track]')
        if not itemid: return
        method = getattr(player, 'info_'+itype)
        method(itemid)
    else:
        # invalid command
        raise ArgumentError(f"invalid command '{cmd}'")


def main():
    helpextra = '''
COMMAND:
  play
  pause
  stop
  next
  prev
  powerron
  poweroff
  vup
  vdown
  volume [n]
  playing
  setcurrent <n>
  playinglistinfo <n>
  search [artists|albums|tracks] TERM
  enqueue [artists|albums|tracks] ITEMS
  info [artists|albums|tracks] ITEM

  NOTE: ITEM for enqueue and info commands is the database id, as returned from search.
'''
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description='A simple script for interacting with the Logitech Media Server.',
                                     epilog=helpextra)
    parser.add_argument('-a','--host',
                        help='LMS hostname', required=True)
    parser.add_argument('-p','--port', type=int, default=9000,
                        help='LMS port (default: %(default)s)')
    parser.add_argument('-n','--player', required=True,
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
    parser.add_argument('-f','--filter-term', action='store_true',
                        help='apply the search term as a filter expression')
    parser.add_argument('-e','--enqueue-method', default='add',
                        choices=['load','insert','add'],
                        help='enqueueing method')
    parser.add_argument('command', nargs='?', default=None,
                        help='player command')
    parser.add_argument('args', nargs='*', help='command arguments')
    
    args = parser.parse_args()
    #print("**", args)
    player = Player(args.player, args.host, args.port)
    if args.zero_indexing:
        player.natural_indexing = False
    # status header
    if args.status_header:
        print_status(player, not args.zero_indexing)        
    if args.command is not None:
        try:
            dispatch_command(player, args)
        except ArgumentError as err:
            parser.error(str(err))
    # exit player status 
    if args.status:
        print_status(player, not args.zero_indexing)

        
if __name__ == '__main__':
    main()


