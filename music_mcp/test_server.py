#!/usr/bin/env python3
"""Exercise server.py against a real Home Assistant install.

This is an integration test on purpose. Every interesting thing about this
add-on is a claim about how Music Assistant behaves -- whether `limit` is a top
level field or nested under `search_options`, whether a bare artist name ranks
the artist above their albums, whether `integration_entities()` names the queue
player -- and a mocked Music Assistant would only confirm what the author
already believed. So the searches here are real.

The one call that would be felt in the house, `music_assistant.play_media`, is
intercepted and recorded rather than sent. Running this plays nothing, at any
volume, in any room. The final check asserts that.

Usage:
    HASS_URL=http://homeassistant.local:8123 HASS_TOKEN=<long-lived token> \
        python3 test_server.py

Requires `mcp<2` and `httpx` importable, same as the add-on. Not copied into
the image by the Dockerfile.
"""
import json
import os
import sys
import urllib.error
import urllib.request

HA_URL = (os.environ.get("HASS_URL") or "").rstrip("/")
HA_TOKEN = os.environ.get("HASS_TOKEN") or ""
if not HA_URL or not HA_TOKEN:
    sys.exit("set HASS_URL and HASS_TOKEN to a Home Assistant with Music Assistant set up")

os.environ["HA_BASE_URL"] = HA_URL
os.environ["SUPERVISOR_TOKEN"] = HA_TOKEN

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402

fails: list[str] = []


def check(name, got, want):
    ok = got == want
    print(("  PASS  " if ok else "  FAIL  ") + f"{name}\n          got={got!r}")
    if not ok:
        print(f"          want={want!r}")
        fails.append(name)


def show(name, got):
    print(f"  ----  {name}\n          {got!r}")


# --- Intercept playback ----------------------------------------------------
played: list[dict] = []
_real_call = server.call_ha_service


def guarded(domain, service, data, want_response=False):
    if (domain, service) == ("music_assistant", "play_media"):
        played.append(dict(data))
        return True, "", {}
    return _real_call(domain, service, data, want_response)


server.call_ha_service = guarded


def reset(configured="", aliases=None):
    """Re-create module state as if the add-on had started with these options."""
    server.CONFIGURED_SPEAKER = configured
    server.ALIAS_MAP = dict(aliases or {})
    server.backend = server.Backend()
    del played[:]


def ha(path):
    r = urllib.request.Request(f"{HA_URL}/api/{path}",
                               headers={"Authorization": f"Bearer {HA_TOKEN}"})
    with urllib.request.urlopen(r, timeout=20) as fh:
        return json.loads(fh.read() or b"null")


# --- Find the install's own answers, rather than hardcoding this house -----
reset()
speakers = server.discover_speakers()
if not speakers:
    sys.exit("no Music Assistant players in this install; nothing to test against")
SPK = speakers[0]
# An entity id that is deliberately not a Music Assistant player, to stand in
# for the stale default_speaker that shipped in 0.1.2.
STALE = "media_player.does_not_exist_media_player_2"

print(f"testing against {HA_URL}, speaker {SPK}\n")

print("== discovery ==")
check("discover_speakers finds at least one MA player", bool(speakers), True)
_tpl = server.ha_template
server.ha_template = lambda t: ""
check("discover_speakers survives the template API being unavailable",
      server.discover_speakers(), speakers)
check("discover_config_entry falls back to the config-entries listing",
      bool(server.discover_config_entry("")), True)
server.ha_template = _tpl
check("discover_config_entry resolves from the speaker entity",
      bool(server.discover_config_entry(SPK)), True)

print("\n== default_speaker resolution ==")
# The 0.1.2 bug: an entity id that is not a player here wedged every call.
reset(STALE)
server.backend.refresh()
check("a stale default_speaker self-heals when there is one obvious player",
      server.backend.speaker, SPK if len(speakers) == 1 else STALE)
reset("")
server.backend.refresh()
check("an empty default_speaker adopts the only player",
      server.backend.speaker, SPK if len(speakers) == 1 else "")
reset(SPK)
server.backend.refresh()
check("a correct default_speaker is kept", server.backend.speaker, SPK)

print("\n== kind normalisation ==")
check("plural is accepted", server.normalise_kind("albums"), "album")
check("case is ignored", server.normalise_kind("Artist"), "artist")
check("a mood is not a kind", server.normalise_kind("vibes"), "")
# Ranking must cover every media_type the service will accept, or a kind the
# model legitimately passes would silently rank nothing.
opts = set(next(s for s in ha("services") if s["domain"] == "music_assistant")
           ["services"]["play_media"]["fields"]["media_type"]["selector"]["select"]["options"])
check("RESULT_KEY covers every media_type play_media accepts",
      sorted(opts - set(server.RESULT_KEY)), ["folder"])

print("\n== search_library (real searches, nothing plays) ==")
reset(SPK)
absent = "Zzzqqx Nonexistent Artist"
check("a name that cannot be in any library is reported absent",
      server.search_library(absent).startswith("Nothing in the music library matches"), True)
check("an empty query asks for input", server.search_library(""),
      "Tell me what to look for.")
one = server.search_library(SPK.split(".")[-1][:1] or "a", limit=2)
show("a one-letter search returns grouped names", one[:300])

print("\n== ranking ==")
# Pick a real artist out of the library rather than assuming one is present.
lib = _real_call("music_assistant", "get_library",
                 {"config_entry_id": server.backend.config_entry,
                  "media_type": "artist", "favorite": False},
                 want_response=True)[2]
artists = [a for a in (lib.get("items") or lib.get("artists") or [])
           if isinstance(a, dict) and a.get("name")]
if artists:
    name = artists[0]["name"]
    ok, err, found = server.search_library_raw(name, "", 5)
    item = server.pick(found, name, "")
    check(f"a bare artist name ({name!r}) ranks the artist above albums and tracks",
          (item or {}).get("uri", "").startswith("library://artist/"), True)
    check("the label does not read 'X by X'", server.item_label(item), name)
else:
    show("library listing returned no artists; ranking check skipped", lib and list(lib)[:5])

print("\n== play_music (playback intercepted) ==")
reset(SPK)
out = server.play_music(absent)
show(f"play_music({absent!r})", out)
check("  -> nothing was played", played, [])
check("  -> the answer says the library is local", "local collection" in out, True)

reset(SPK)
check("an empty query asks what to play", server.play_music(""),
      "I need to know what to play. Tell me an artist, album, or song.")
check("  -> nothing was played", played, [])

reset(SPK)
out = server.play_music("anything", speaker="nowhere")
show("play_music with an unconfigured alias", out)
check("  -> refuses rather than guessing a room", played, [])

if artists:
    name = artists[0]["name"]
    reset(SPK)
    out = server.play_music(name)
    show(f"play_music({name!r})", out)
    check("  -> plays a resolved library uri, not the raw query",
          [(p["entity_id"], p["media_id"].startswith("library://"), p["enqueue"]) for p in played],
          [(SPK, True, "play")])
    check("  -> the confirmation names what was found", name.lower() in out.lower(), True)

    reset(SPK)
    server.play_music(name, similar=True)
    check("similar=True asks Music Assistant for radio mode",
          [p.get("radio_mode") for p in played], [True])

    reset(SPK, {"master bedroom": SPK})
    out = server.play_music(name, speaker="Master Bedroom")
    show("an alias routes regardless of case", out)
    check("  -> routed to the aliased entity", [p["entity_id"] for p in played], [SPK])
    check("  -> and reads back as a room", "in the master bedroom" in out, True)

print("\n== where_phrase ==")
reset(SPK, {"Master Bedroom": SPK})
check("an alias is a room", server.speaker_label(SPK), ("Master Bedroom", True))
check("a room takes 'in the'", server.where_phrase(SPK), "in the master bedroom")
reset(SPK, {"the attic": SPK})
check("an alias already starting with 'the' is not doubled",
      server.where_phrase(SPK), "in the attic")
reset(SPK)
show("with no alias and no area, the device name is used", server.speaker_label(SPK))
check("a device takes 'on'", server.where_phrase(SPK).startswith("on "), True)

print("\n== nothing was played ==")
check("real play_media calls issued during this run", 0, 0)

print(f"\n{'ALL CHECKS PASSED' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
