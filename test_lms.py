#!/usr/bin/env python3
"""Unit tests for lms.py

These tests never touch a real network. All calls to urllib.request.urlopen
are mocked, so the suite runs instantly and works in CI with no LMS server
available.

Run with:
    python -m unittest test_lms.py -v
or, if you install pytest:
    pytest test_lms.py -v
"""
import io
import json
import unittest
from unittest.mock import patch, MagicMock

import lms


# ---------------------------------------------------------------------------
# Pure helper functions (no network, no Player instance needed)
# ---------------------------------------------------------------------------

class TestSafeInt(unittest.TestCase):
    def test_valid_int_string(self):
        self.assertEqual(lms._safeint("42"), 42)

    def test_invalid_string_returns_negative_one(self):
        self.assertEqual(lms._safeint("not-a-number"), -1)

    def test_none_returns_negative_one(self):
        self.assertEqual(lms._safeint(None), -1)

    def test_empty_string_returns_negative_one(self):
        self.assertEqual(lms._safeint(""), -1)

    def test_whitespace_returns_negative_one(self):
        self.assertEqual(lms._safeint("   "), -1)

    def test_zero_string(self):
        self.assertEqual(lms._safeint("0"), 0)

    def test_negative_integer_string(self):
        self.assertEqual(lms._safeint("-42"), -42)

    def test_integer_input(self):
        self.assertEqual(lms._safeint(123), 123)


class TestFormatDuration(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(lms.format_duration(65), "1:05")

    def test_zero(self):
        self.assertEqual(lms.format_duration(0), "0:00")

    def test_over_an_hour(self):
        # 3661 seconds = 61 minutes, 1 second (no separate hour field)
        self.assertEqual(lms.format_duration(3661), "61:01")

    def test_accepts_float_input(self):
        self.assertEqual(lms.format_duration(90.7), "1:30")

    def test_under_a_minute(self):
        self.assertEqual(lms.format_duration(59), "0:59")

    def test_exactly_one_minute(self):
        self.assertEqual(lms.format_duration(60), "1:00")

    def test_one_second_before_an_hour(self):
        self.assertEqual(lms.format_duration(3599), "59:59")

    def test_exactly_one_hour(self):
        self.assertEqual(lms.format_duration(3600), "60:00")


# ---------------------------------------------------------------------------
# Helper for constructing a Servers and Players without hitting the network
# ---------------------------------------------------------------------------

def make_server():
    return lms.Server(host="testhost", port="9000")

def make_player(mac="00:11:22:33:44:55"):
    """Build a Player instance while skipping the real find_player() lookup."""
    player = lms.Player(make_server(), mac, "Kitchen")
    return player


# ---------------------------------------------------------------------------
# Server.request() - the low-level JSON-RPC transport
# ---------------------------------------------------------------------------

class TestServerRequest(unittest.TestCase):
    @staticmethod
    def _mock_response(result):
        payload = json.dumps({"result": result}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        return mock_resp

    @patch("lms.urllib.request.urlopen")
    def test_request_returns_result_field(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response({"_volume": 42})
        server = make_server()
        result = server.request(1, "mixer", "volume", "?")
        self.assertEqual(result, {"_volume": 42})

    @patch("lms.urllib.request.urlopen")
    def test_connection_failure_raises_lms_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = lms.urllib.error.URLError("connection refused")
        server = make_server()
        with self.assertRaises(lms.LMSConnectionError):
            server.request(0, "status")

    @patch("lms.urllib.request.urlopen")
    def test_string_params_are_split_into_a_list(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response({"ok": True})
        server = make_server()
        server.request(1, "mixer", "volume", "?")
        sent_body = mock_urlopen.call_args[0][1]
        sent_data = json.loads(sent_body.decode("utf-8"))
        self.assertEqual(sent_data["params"][1], ["mixer", "volume", "?"])

    @patch("lms.urllib.request.urlopen")
    def test_invalid_json_raises_lms_connection_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{"
        mock_urlopen.return_value = mock_resp
        server = make_server()
        with self.assertRaises(lms.LMSConnectionError):
            server.request(1, "status")

    @patch("lms.urllib.request.urlopen")
    def test_missing_result_field_raises_lms_connection_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_urlopen.return_value = mock_resp
        server = make_server()
        with self.assertRaises(lms.LMSConnectionError):
            server.request(1, "status")

    @patch("lms.urllib.request.urlopen")
    def test_request_payload_contains_expected_method_and_player(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response({"ok": True})
        server = make_server()
        server.request(1, "status")
        sent_body = mock_urlopen.call_args[0][1]
        sent_data = json.loads(sent_body.decode("utf-8"))
        self.assertEqual(sent_data["method"], "slim.request")
        self.assertEqual(sent_data["params"][0], 1)


# ---------------------------------------------------------------------------
# Player._build_search() & _build_match() - search-term / parameter-search parsing
# ---------------------------------------------------------------------------

class TestBuildSearch(unittest.TestCase):
    def setUp(self):
        self.player = make_player()

    def test_plain_term_becomes_search_prefix(self):
        self.assertEqual(self.player._build_search("miles"), "search:miles")

    def test_empty_term_with_no_param_is_empty(self):
        self.assertEqual(self.player._build_search(""), "")

    def test_param_search_uses_param_as_prefix(self):
        result = self.player._build_match("artist_id", "123")
        self.assertEqual(result, "artist_id:123")

    def test_plain_term_is_trimmed(self):
        self.assertEqual(
            self.player._build_search("  miles  "),
            "search:miles",
        )

    def test_param_search_term_is_trimmed(self):
        self.assertEqual(
            self.player._build_match("artist_id", " 123 "),
            "artist_id:123",
        )

    def test_trim_id_keeps_only_first_field(self):
        self.player.trim_id = True
        term = "123" + " " * 5 + "Miles Davis"  # first 8 chars -> "123     "
        result = self.player._build_match("artist_id", term)
        self.assertEqual(result, "artist_id:123")


# ---------------------------------------------------------------------------
# Player._enqueue() - shared logic behind enqueue_artists/albums/tracks
# ---------------------------------------------------------------------------

class TestEnqueue(unittest.TestCase):
    def setUp(self):
        self.player = make_player()
        self.player.player_request = MagicMock(return_value={})

    def test_invalid_method_raises(self):
        with self.assertRaises(lms.LMSArgumentError):
            self.player._enqueue("track", ["1"], "bogus")

    def test_empty_items_is_a_noop(self):
        self.player._enqueue("track", [], "add")
        self.player.player_request.assert_not_called()

    def test_track_ids_are_joined_into_one_csv_request(self):
        self.player._enqueue("track", ["1", "2", "3"], "add")
        self.player.player_request.assert_called_once_with(
            "playlistcontrol", "cmd:add", "track_id:1,2,3"
        )

    def test_play_method_maps_to_server_load_command(self):
        self.player._enqueue("album", ["7"], "play")
        self.player.player_request.assert_called_once_with(
            "playlistcontrol", "cmd:load", "album_id:7"
        )

    def test_album_ids_are_sent_one_request_each(self):
        self.player._enqueue("album", ["1", "2"], "add")
        self.assertEqual(self.player.player_request.call_count, 2)


# ---------------------------------------------------------------------------
# Player.volume() - clamping behaviour
# ---------------------------------------------------------------------------

class TestVolume(unittest.TestCase):
    CURRENT_VOLUME = 50
    def setUp(self):
        self.player = make_player()
        self.player.player_request = MagicMock(return_value={'_volume':self.CURRENT_VOLUME})

    def test_value_above_100_is_clamped(self):
        self.player.volume(150)
        self.player.player_request.assert_called_once_with("mixer", "volume", 100)

    def test_value_below_0_is_clamped(self):
        self.player.volume(-10)
        self.player.player_request.assert_called_once_with("mixer", "volume", 0)

    def test_value_zero_is_not_modified(self):
        self.player.volume(0)
        self.player.player_request.assert_called_once_with("mixer", "volume", 0)

    def test_value_100_is_not_modified(self):
        self.player.volume(100)
        self.player.player_request.assert_called_once_with("mixer", "volume", 100)

    def test_no_argument_returns_current_volume(self):
        self.assertEqual(self.player.volume(), self.CURRENT_VOLUME)
        self.player.player_request.assert_called_once_with("mixer", "volume", "?")


# ---------------------------------------------------------------------------
# Command dispatch / argument validation
# ---------------------------------------------------------------------------

class TestDispatchCommand(unittest.TestCase):
    def setUp(self):
        self.player = make_player()

    @staticmethod
    def _args(command, args=None, **overrides):
        ns = MagicMock()
        ns.command = command
        ns.args = args or []
        ns.trim_id = False
        ns.maxitems = 9999
        ns.enqueue_method = "add"
        ns.param_search = False
        for key, value in overrides.items():
            setattr(ns, key, value)
        return ns

    def test_unknown_command_raises(self):
        with self.assertRaises(lms.LMSArgumentError):
            lms.dispatch_command(self.player, self._args("bogus"))

    def test_unique_prefix_resolves_to_full_command(self):
        self.player.next = MagicMock()
        lms.dispatch_command(self.player, self._args("ne"))  # only "next" matches
        self.player.next.assert_called_once()

    def test_ambiguous_prefix_raises(self):
        # "p" matches play, pause, prev, poweron, poweroff
        with self.assertRaises(lms.LMSArgumentError):
            lms.dispatch_command(self.player, self._args("p"))

    def test_search_without_type_raises(self):
        with self.assertRaises(lms.LMSArgumentError):
            lms.command_search(self.player, self._args("search", []))

    def test_search_with_invalid_type_raises(self):
        with self.assertRaises(lms.LMSArgumentError):
            lms.command_search(self.player, self._args("search", ["bogus"]))

    def test_enqueue_without_item_raises(self):
        with self.assertRaises(lms.LMSArgumentError):
            lms.command_enqueue(self.player, self._args("enqueue", ["tracks"]))

    def test_match_param_without_colon_raises(self):
        with self.assertRaises(lms.LMSArgumentError):
            lms.command_match(
                self.player,
                self._args(
                    "match",
                    ["artists", "123"]
                ),
            )

    def test_invalid_match_param_key_raises(self):
        with self.assertRaises(lms.LMSArgumentError):
            lms.command_match(
                self.player,
                self._args(
                    "match",
                    ["artists", "foo:1"]
                ),
            )


if __name__ == "__main__":
    unittest.main()
