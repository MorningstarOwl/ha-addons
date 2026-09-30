"""
Music MCP Server
----------------
MCP server for playing a *local* music library through Music Assistant.
Exposes a small, opinionated tool set so a voice assistant can play music
without picking the wrong device and without inventing queries the library
cannot answer.

Reads options from /data/options.json (injected by HA Supervisor), calls Home
Assistant's REST API via the supervisor proxy using SUPERVISOR_TOKEN, and
returns confirmation messages as plain spoken English suitable for TTS.

Why v0.2 is shaped the way it is
--------------------------------
v0.1 was written against a Music Assistant install backed by Spotify, and made
three assumptions that do not survive contact with a file-backed library:

1. It found the MA queue overlay by the entity-id suffix `_media_player_2`.
   That suffix is not MA's doing — it is Home Assistant deduplicating a name
   collision. MA names its player from mDNS, so on an install where the MA
   player's name differs from the base player's, HA never appends `_2` and
   discovery finds nothing. The *reasoning* behind the original code was right
   (you must aim at MA's overlay, not the base player, because the base player
   cannot queue or skip); only the identifier was wrong. Discovery now asks
   Home Assistant which entities the `music_assistant` integration owns, and
   keeps the suffix match as a last resort.

2. It passed the raw user query to `music_assistant.play_media` as `media_id`
   and hoped MA would resolve it. Now it searches first, ranks the hits, plays
   a resolved `library://` uri, and reports the name it actually found. That
   turns "I could not find that" into an answer instead of silence, and stops
   the confirmation message parroting a query that matched nothing.

3. Its tool docstring told the model Music Assistant would "search Spotify".
   MA's search against a filesystem provider is substring matching over the
   local index, so a streaming-shaped query either finds nothing or finds
   something absurd — "jazz radio" matches an album called "Piano Jazz Radio
   Broadcast With Steely Dan". The docstrings now say what the library is and
   what search can do, which is the whole point of an MCP tool.

Scope: this add-on is the *fallback* path for open-ended requests. A house that
answers "play Rumours" with a local sentence trigger does not need an LLM in
the loop for the common case; it needs one for "put on something mellow", and
that is what `search_library` plus `play_music` are for.

MCP SSE endpoint: http://homeassistant.local:8767/sse
"""

import json
import logging
import os
import urllib.parse

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

OPTIONS_FILE = "/data/options.json"
# Overridable so the module can be exercised against a real Home Assistant with
# a long-lived token from a developer machine. Under Supervisor, leave it alone.
SUPERVISOR_BASE = os.environ.get("HA_BASE_URL", "http://supervisor/core")
PORT = 8767
SEARCH_LIMIT = 5

# `music_assistant.search` returns one list per media type. Note that "radio"
# is the one key that is not pluralised, so the mapping is explicit rather than
# a `kind + "s"` guess.
RESULT_KEY = {
    "artist": "artists",
    "album": "albums",
    "track": "tracks",
    "playlist": "playlists",
    "radio": "radio",
    "podcast": "podcasts",
    "audiobook": "audiobooks",
}
# Ranking order when the user did not say what kind of thing they meant. A bare
# artist name means "play this artist", not "play one song of theirs", so
# artists outrank albums outrank tracks.
DEFAULT_ORDER = ("artists", "albums", "playlists", "tracks")


# ---------------------------------------------------------------------------
# Addon options
# ---------------------------------------------------------------------------

def load_options() -> dict:
    try:
        with open(OPTIONS_FILE) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Could not read options.json: {e}")
        return {}


options = load_options()
CONFIGURED_SPEAKER: str = (options.get("default_speaker") or "").strip()
SUPERVISOR_TOKEN: str = os.environ.get("SUPERVISOR_TOKEN", "")

# Build alias map: lowercase friendly name -> entity_id
ALIAS_MAP: dict[str, str] = {
    entry["name"].strip().lower(): entry["entity_id"].strip()
    for entry in options.get("speaker_aliases", [])
    if entry.get("name") and entry.get("entity_id")
}


# ---------------------------------------------------------------------------
# Home Assistant REST helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}


def ha_get(path: str):
    """GET from HA Core REST API via supervisor proxy. Returns parsed JSON or None."""
    if not SUPERVISOR_TOKEN:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{SUPERVISOR_BASE}/api/{path.lstrip('/')}", headers=_headers())
        if r.status_code == 200:
            return r.json()
        log.warning(f"HA GET /{path} returned HTTP {r.status_code}")
    except Exception as e:
        log.warning(f"HA GET /{path} failed: {e}")
    return None


def ha_template(template: str) -> str:
    """Render a Jinja template through HA. Returns the text, or "" on failure.

    /api/template answers text/plain, not JSON, so this is deliberately not
    routed through ha_get.
    """
    if not SUPERVISOR_TOKEN:
        return ""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(f"{SUPERVISOR_BASE}/api/template",
                            json={"template": template}, headers=_headers())
        if r.status_code == 200:
            out = r.text.strip()
            return "" if out in ("None", "none", "") else out
        log.warning(f"HA template returned HTTP {r.status_code}")
    except Exception as e:
        log.warning(f"HA template failed: {e}")
    return ""


def call_ha_service(domain: str, service: str, data: dict,
                    want_response: bool = False) -> tuple[bool, str, dict]:
    """POST /api/services/<domain>/<service> via the supervisor proxy.

    Returns (ok, error_message, service_response). On success error_message is
    empty. Failures are natural-language strings the caller can hand straight
    back to the assistant for TTS read-back.
    """
    if not SUPERVISOR_TOKEN:
        return False, ("SUPERVISOR_TOKEN is not set. The addon must run under "
                       "Home Assistant Supervisor."), {}

    url = f"{SUPERVISOR_BASE}/api/services/{domain}/{service}"
    if want_response:
        url += "?" + urllib.parse.urlencode({"return_response": "true"})
    try:
        with httpx.Client(timeout=20) as client:
            r = client.post(url, json=data, headers=_headers())
    except httpx.HTTPError as e:
        return False, f"Could not reach Home Assistant: {e}", {}

    if r.status_code >= 400:
        snippet = r.text[:200].replace("\n", " ").strip()
        return False, f"Home Assistant returned HTTP {r.status_code}: {snippet}", {}

    body = {}
    if want_response:
        try:
            body = (r.json() or {}).get("service_response") or {}
        except ValueError:
            body = {}
    return True, "", body


# ---------------------------------------------------------------------------
# Discovery: which speaker, and which Music Assistant config entry
# ---------------------------------------------------------------------------

def discover_speakers() -> list[str]:
    """Entity ids of the Music Assistant queue players, best source first.

    Three sources, tried in order, because each can be unavailable on its own:

    1. `integration_entities('music_assistant')` — authoritative. This is HA's
       own record of which entities the integration created, so it does not
       depend on entity naming or on the player's current state.
    2. state attributes — `app_id: music_assistant`, or the presence of
       `active_queue`. Works when the template API is not reachable.
    3. the `_media_player_2` suffix — what v0.1 assumed. Kept last because on
       some installs it really is the name, and it costs nothing to try.
    """
    rendered = ha_template(
        "{{ integration_entities('music_assistant') "
        "| select('match', 'media_player\\\\.') | list | join(',') }}")
    if rendered:
        found = sorted(e.strip() for e in rendered.split(",") if e.strip())
        if found:
            return found

    states = ha_get("states")
    if not isinstance(states, list):
        return []
    players = [s for s in states
               if isinstance(s, dict) and s.get("entity_id", "").startswith("media_player.")]
    by_attr = sorted(s["entity_id"] for s in players
                     if (s.get("attributes") or {}).get("app_id") == "music_assistant"
                     or "active_queue" in (s.get("attributes") or {}))
    if by_attr:
        return by_attr
    return sorted(s["entity_id"] for s in players
                  if s["entity_id"].endswith("_media_player_2"))


def discover_config_entry(speaker: str) -> str:
    """The `music_assistant` config entry id, which its services require.

    `config_entry_id(<entity>)` is the cheap way when a speaker is known;
    otherwise fall back to the config-entries listing filtered by domain.
    """
    if speaker:
        entry = ha_template("{{ config_entry_id('%s') }}" % speaker)
        if entry:
            return entry
    entries = ha_get("config/config_entries/entry?domain=music_assistant")
    if isinstance(entries, list):
        loaded = [e for e in entries if isinstance(e, dict) and e.get("entry_id")]
        for e in loaded:
            if e.get("state") == "loaded":
                return e["entry_id"]
        if loaded:
            return loaded[0]["entry_id"]
    return ""


class Backend:
    """Lazily-resolved view of the Music Assistant backend.

    Home Assistant may not be answering yet when the add-on starts, and a
    stale `default_speaker` must not wedge the add-on for its whole lifetime.
    So both the speaker and the config entry are resolved on demand and
    re-resolved whenever they are still missing.
    """

    def __init__(self) -> None:
        self.speaker = ""
        self.config_entry = ""
        self.known: list[str] = []

    def refresh(self) -> None:
        self.known = discover_speakers()
        if CONFIGURED_SPEAKER and CONFIGURED_SPEAKER in self.known:
            self.speaker = CONFIGURED_SPEAKER
        elif CONFIGURED_SPEAKER and not self.known:
            # Nothing discovered; trust the operator over our own blindness.
            self.speaker = CONFIGURED_SPEAKER
        elif len(self.known) == 1:
            # The v0.1 failure mode, fixed: one obvious answer, so use it and
            # say loudly that the configured value was ignored.
            if CONFIGURED_SPEAKER:
                log.warning(
                    f"default_speaker {CONFIGURED_SPEAKER!r} is not a Music Assistant "
                    f"player in this install; using the only one there is, {self.known[0]}. "
                    "Update the Configuration tab to silence this.")
            self.speaker = self.known[0]
        else:
            self.speaker = CONFIGURED_SPEAKER
        self.config_entry = discover_config_entry(self.speaker)

    def ready(self) -> tuple[str, str]:
        """(speaker, config_entry), resolving on first use and after a failure."""
        if not self.speaker or not self.config_entry:
            self.refresh()
        return self.speaker, self.config_entry


backend = Backend()


def resolve_speaker(speaker_arg: str) -> str:
    """Resolve a friendly alias or entity_id to a final entity_id string."""
    s = (speaker_arg or "").strip()
    if not s:
        return backend.ready()[0]
    return ALIAS_MAP.get(s.lower(), s)


def speaker_label(entity_id: str) -> tuple[str, bool]:
    """The nicest spoken name for a speaker, and whether it names a room.

    Alias first, because the operator chose it to be the room's name. Then the
    entity's area, for installs where the Music Assistant player carries one.
    Then friendly_name, then the bare id. The boolean is what lets the caller
    say "in the master bedroom" rather than "on master bedroom": a room takes a
    different preposition from a device, and this add-on's whole output contract
    is speakable English.
    """
    for alias, eid in ALIAS_MAP.items():
        if eid == entity_id:
            return alias, True
    area = ha_template("{{ area_name('%s') }}" % entity_id)
    if area:
        return area, True
    name = ha_template("{{ state_attr('%s', 'friendly_name') }}" % entity_id)
    if name:
        return name, False
    bare = entity_id.split(".", 1)[-1]
    for suffix in ("_media_player_2", "_media_player"):
        if bare.endswith(suffix):
            bare = bare[: -len(suffix)]
            break
    return (bare.replace("_", " ").strip() or entity_id), False


def where_phrase(entity_id: str) -> str:
    """"in the master bedroom", or "on home-assistant-voice-0994d0"."""
    label, is_room = speaker_label(entity_id)
    low = label.lower()
    if is_room:
        return f"in {low}" if low.startswith("the ") else f"in the {low}"
    return f"on {label}"


# ---------------------------------------------------------------------------
# Search and ranking
# ---------------------------------------------------------------------------

def search_library_raw(query: str, kind: str, limit: int) -> tuple[bool, str, dict]:
    """Ask Music Assistant to search its index. Returns (ok, error, results)."""
    _, entry = backend.ready()
    if not entry:
        return False, ("I cannot reach Music Assistant. The music_assistant "
                       "integration does not look set up in Home Assistant."), {}
    # `limit` is top level here. The service description advertises a nested
    # `search_options: {limit, library_only}` object, and Music Assistant 2.10.4
    # rejects that form with HTTP 400 — measured, not assumed.
    data = {"config_entry_id": entry, "name": query, "limit": limit}
    if kind:
        data["media_type"] = kind
    ok, err, resp = call_ha_service("music_assistant", "search", data, want_response=True)
    if not ok:
        # A bad config entry is the likely cause, so drop it and re-resolve
        # on the next call rather than failing identically forever.
        backend.config_entry = ""
        return False, err, {}
    return True, "", resp


def pick(found: dict, query: str, kind: str) -> dict | None:
    """Best hit from a search response, or None.

    Exact name matches are preferred across every media type before any
    substring match is considered, so "play Rumours" lands on the album rather
    than on a track whose title merely contains the word.
    """
    keys = (RESULT_KEY[kind],) if kind in RESULT_KEY else DEFAULT_ORDER
    q = (query or "").strip().lower()
    for exact_only in (True, False):
        for key in keys:
            for item in found.get(key) or []:
                if not isinstance(item, dict) or not item.get("uri"):
                    continue
                if exact_only and (item.get("name") or "").strip().lower() != q:
                    continue
                return item
    return None


def item_label(item: dict) -> str:
    """"Rumours by Fleetwood Mac" — what actually got played, for read-back."""
    name = (item.get("name") or "").strip() or item.get("uri", "something")
    who = next((a.get("name") for a in (item.get("artists") or []) if a.get("name")), "")
    if who and who.strip().lower() != name.strip().lower():
        return f"{name} by {who}"
    return name


def normalise_kind(kind: str) -> str:
    k = (kind or "").strip().lower().rstrip("s")
    return k if k in RESULT_KEY else ""


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("Music MCP Server", host="0.0.0.0", port=PORT)


@mcp.tool()
def play_music(query: str, speaker: str = "", kind: str = "", similar: bool = False) -> str:
    """
    Play music from this house's own music library on a speaker.

    THE LIBRARY IS LOCAL FILES. No Spotify, no Apple Music, no YouTube, no
    internet radio is connected. Everything that can be played is a FLAC or
    MP3 file on the house NAS, indexed by Music Assistant.

    Search is SUBSTRING MATCHING over that index. It is not fuzzy, semantic, or
    web-backed. A query matches only if its words literally appear in the name
    of an artist, album, track or playlist that exists on disk.

    What that means for the query you send:

    - Name a thing that exists: "Rumours", "Fleetwood Mac", "Black Sabbath",
      "Dark Side of the Moon".
    - Do NOT send moods, genres or vibes. They usually find nothing, and
      sometimes find something absurd: "jazz radio" matches an album named
      "Piano Jazz Radio Broadcast With Steely Dan", and the house would play
      Steely Dan.
    - Do NOT add words like "playlist", "album", "radio" or "songs" as
      decoration. Use the kind argument if you want to narrow the search.
    - If the request is open-ended ("put on something mellow", "something like
      Portishead"), call search_library FIRST to see what is actually here,
      then play a real name from what it returns. If the artist the user named
      is not in the library, tell them that instead of playing a near-miss.

    Arguments:
      query    The name to look for: an artist, album, track or playlist.
      speaker  A room alias configured in this add-on, or a full media_player
               entity_id. Omit it to use the default speaker. Only pass it when
               the user names a room.
      kind     Optional. One of artist, album, track, playlist. Pass it when
               the user was explicit: "play the album Rumours" -> kind="album".
      similar  Optional. Set true only for "something like X" requests. Plays
               the match and then continues with similar music drawn from this
               same local library, so the seed must itself be in the library.

    Returns a spoken-English sentence naming what was actually found and where
    it is playing, or plain-English detail about why nothing played.
    """
    q = (query or "").strip()
    if not q:
        return "I need to know what to play. Tell me an artist, album, or song."

    kind = normalise_kind(kind)
    target = resolve_speaker(speaker)
    if not target:
        return ("No speaker is configured and I could not find a Music Assistant "
                "player to use. Set default_speaker in the addon Configuration tab.")
    if not target.startswith("media_player."):
        return (f"I do not know a speaker called {target}. "
                "Check the speaker aliases in the addon options.")

    ok, err, found = search_library_raw(q, kind, SEARCH_LIMIT)
    if not ok:
        log.warning(f"search failed for {q!r}: {err}")
        return f"I could not search the music library. {err}"

    item = pick(found, q, kind)
    if not item:
        article = "an" if kind in ("album", "artist", "audiobook") else "a"
        what = f" as {article} {kind}" if kind else ""
        return (f"I could not find {q}{what} in the music library. "
                "It is a local collection, so if it is not on the NAS I cannot play it.")

    label = item_label(item)
    log.info(f"play_music: query={q!r} kind={kind or 'any'} -> {item.get('uri')} "
             f"({label}) speaker={target} similar={similar}")

    data = {"entity_id": target, "media_id": item["uri"], "enqueue": "play"}
    if similar:
        data["radio_mode"] = True
    ok, err, _ = call_ha_service("music_assistant", "play_media", data)
    if not ok:
        log.warning(f"play_media failed: {err}")
        return f"I found {label} but could not start playback. {err}"

    more = " and similar music after it" if similar else ""
    return f"Playing {label}{more} {where_phrase(target)}."


@mcp.tool()
def search_library(query: str, kind: str = "", limit: int = 8) -> str:
    """
    Look up what is actually in this house's music library. Nothing plays.

    Use this before play_music whenever you are not certain the thing the user
    asked for exists here — especially for open-ended requests ("something
    mellow", "something like Portishead"), or when they named an artist you
    have no reason to think is on this NAS. The library is a personal
    collection of a few thousand albums, not a streaming catalogue: plenty of
    well-known artists are simply absent.

    Matching is substring only, so search for a short distinctive fragment of a
    name rather than a description. Searching for a genre or a mood will not
    work; searching for an artist you suspect is here will.

    Arguments:
      query  A name or part of a name to look for.
      kind   Optional. One of artist, album, track, playlist, to list only
             that sort of result.
      limit  Optional. How many of each sort to return.

    Returns the matching names, grouped by sort, or a plain statement that
    nothing in the library matches. Feed one of the names it returns back to
    play_music as the query.
    """
    q = (query or "").strip()
    if not q:
        return "Tell me what to look for."

    kind = normalise_kind(kind)
    limit = max(1, min(int(limit or 8), 25))
    ok, err, found = search_library_raw(q, kind, limit)
    if not ok:
        return f"I could not search the music library. {err}"

    lines = []
    for key in ("artists", "albums", "playlists", "tracks"):
        if kind and RESULT_KEY[kind] != key:
            continue
        items = [i for i in (found.get(key) or []) if isinstance(i, dict) and i.get("name")]
        if items:
            lines.append(f"{key.capitalize()}: " + "; ".join(item_label(i) for i in items))
    if not lines:
        return (f"Nothing in the music library matches {q}. "
                "It is a local collection, so it may simply not be here.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def startup_report() -> None:
    """Log what was resolved, so the Log tab answers "why is it doing that"."""
    if not SUPERVISOR_TOKEN:
        log.warning("SUPERVISOR_TOKEN not set — HA REST calls will fail. "
                    "Is this running outside Supervisor?")
        return

    backend.refresh()
    if backend.known:
        log.info(f"Discovered {len(backend.known)} Music Assistant player(s):")
        for i, eid in enumerate(backend.known, 1):
            log.info(f"  {i}. {eid}")
    else:
        log.warning("No Music Assistant players discovered. Is the Music Assistant "
                    "integration set up, and are its players exposed to Home Assistant?")

    if ALIAS_MAP:
        log.info(f"Speaker aliases ({len(ALIAS_MAP)}):")
        for alias, eid in ALIAS_MAP.items():
            mark = "" if not backend.known or eid in backend.known else "  <- not a known MA player"
            log.info(f"  '{alias}' -> {eid}{mark}")
    else:
        log.info("No speaker aliases configured. Add them under speaker_aliases in the "
                 "Configuration tab to let the assistant route by room name.")

    log.info(f"Default speaker: {backend.speaker or '(none resolved)'}")
    log.info(f"Music Assistant config entry: {backend.config_entry or '(not found)'}")


if __name__ == "__main__":
    log.info(f"Starting Music MCP SSE server on port {PORT}...")
    startup_report()
    mcp.run(transport="sse")
