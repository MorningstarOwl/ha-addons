"""
Music MCP Server
----------------
MCP server for media playback through Music Assistant. Exposes a small,
opinionated tool set so a voice assistant can play music without picking
the wrong device or getting confused by Music Assistant's dual-entity
setup (base LVA player vs. MA queue overlay).

Reads options from /data/options.json (injected by HA Supervisor),
calls Home Assistant's REST API via the supervisor proxy using
SUPERVISOR_TOKEN, and returns confirmation messages as plain spoken
English suitable for TTS read-back.

Phase 1.2: auto-discovers Music Assistant queue entities at startup and
logs them so the correct entity_id is always visible in the addon log.
Supports a speaker_aliases map (friendly name → entity_id) so voice
assistants can say "office" instead of a full entity_id.

MCP SSE endpoint: http://homeassistant.local:8767/sse
"""

import json
import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

OPTIONS_FILE = "/data/options.json"
SUPERVISOR_BASE = "http://supervisor/core"
PORT = 8767


# ---------------------------------------------------------------------------
# Load addon options
# ---------------------------------------------------------------------------

def load_options() -> dict:
    try:
        with open(OPTIONS_FILE) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Could not read options.json: {e}")
        return {}


options = load_options()
DEFAULT_SPEAKER: str = options.get("default_speaker", "").strip()
SUPERVISOR_TOKEN: str = os.environ.get("SUPERVISOR_TOKEN", "")

# Build alias map: lowercase friendly name → entity_id
ALIAS_MAP: dict[str, str] = {
    entry["name"].strip().lower(): entry["entity_id"].strip()
    for entry in options.get("speaker_aliases", [])
    if entry.get("name") and entry.get("entity_id")
}


# ---------------------------------------------------------------------------
# Home Assistant REST helpers
# ---------------------------------------------------------------------------

def ha_get(path: str):
    """GET from HA Core REST API via supervisor proxy. Returns parsed JSON or None."""
    if not SUPERVISOR_TOKEN:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                f"{SUPERVISOR_BASE}/api/{path.lstrip('/')}",
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning(f"HA GET /{path} failed: {e}")
    return None


def discover_speakers() -> list[str]:
    """Return entity_ids of Music Assistant queue overlay players (_media_player_2)."""
    states = ha_get("states")
    if not isinstance(states, list):
        return []
    return sorted(
        s["entity_id"]
        for s in states
        if isinstance(s, dict)
        and s.get("entity_id", "").startswith("media_player.")
        and s.get("entity_id", "").endswith("_media_player_2")
    )


def resolve_speaker(speaker_arg: str) -> str:
    """Resolve a friendly alias or entity_id to a final entity_id string."""
    s = (speaker_arg or "").strip()
    if not s:
        return DEFAULT_SPEAKER
    return ALIAS_MAP.get(s.lower(), s)


def call_ha_service(domain: str, service: str, data: dict) -> tuple[bool, str]:
    """POST /api/services/<domain>/<service> via the supervisor proxy.

    Returns (ok, error_message). On success, error_message is empty.
    Failure cases are surfaced as natural-language strings the caller can
    return directly to the assistant for TTS read-back.
    """
    if not SUPERVISOR_TOKEN:
        return False, (
            "SUPERVISOR_TOKEN is not set. The addon must run under "
            "Home Assistant Supervisor."
        )

    url = f"{SUPERVISOR_BASE}/api/services/{domain}/{service}"
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(
                url,
                json=data,
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            )
    except httpx.HTTPError as e:
        return False, f"Could not reach Home Assistant: {e}"

    if r.status_code >= 400:
        snippet = r.text[:200].replace("\n", " ").strip()
        return False, f"Home Assistant returned HTTP {r.status_code}: {snippet}"
    return True, ""


def prettify_entity_id(entity_id: str) -> str:
    """media_player.exr1_speaker_media_player_2 -> 'exr1 speaker'"""
    name = entity_id.split(".", 1)[-1]
    for suffix in ("_media_player_2", "_media_player"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", " ").strip() or entity_id


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("Music MCP Server", host="0.0.0.0", port=PORT)


@mcp.tool()
def play_music(query: str, speaker: str = "") -> str:
    """
    Search for music and start playing it on a speaker.

    The query argument is free-form text — an artist name, song name,
    album name, playlist name, or genre description. Music Assistant
    will search Spotify and play the best match. Examples of valid
    queries: "Joanna Newsom", "Sapokanikan", "lo-fi study beats
    playlist", "jazz radio", "Bach cello suites".

    The speaker argument accepts either a friendly alias configured in
    the addon (e.g. "office", "kitchen", "exr1") or a full entity_id
    (e.g. "media_player.exr1_speaker_media_player_2"). Omit it to play
    on the default speaker. Use the alias that matches where the user is
    speaking from when they specify a room, otherwise omit it.

    Returns a confirmation message naming what was played and where.
    """
    q = (query or "").strip()
    if not q:
        return (
            "I need to know what to play. "
            "Tell me an artist, song, album, or genre."
        )

    target = resolve_speaker(speaker)
    if not target:
        return (
            "No speaker is configured. "
            "Set default_speaker in the addon Configuration tab, "
            "or pass a speaker alias."
        )

    if not target.startswith("media_player."):
        return (
            f"'{target}' is not a recognised speaker. "
            "Check that the speaker alias is configured correctly in "
            "the addon options."
        )

    log.info(f"play_music: query={q!r} speaker={target}")
    ok, err = call_ha_service(
        "music_assistant",
        "play_media",
        {
            "entity_id": target,
            "media_id": q,
            "enqueue": "play",
        },
    )
    if not ok:
        log.warning(f"play_media failed: {err}")
        return f"I could not start playback. {err}"

    return f"Playing {q} on {prettify_entity_id(target)}."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info(f"Starting Music MCP SSE server on port {PORT}...")

    if not SUPERVISOR_TOKEN:
        log.warning(
            "SUPERVISOR_TOKEN not set — HA REST calls will fail. "
            "Is this running outside Supervisor?"
        )

    # --- Speaker discovery ---
    discovered = discover_speakers()
    if discovered:
        log.info(f"Discovered {len(discovered)} Music Assistant speaker(s):")
        for i, eid in enumerate(discovered, 1):
            log.info(f"  {i}. {eid}")
        if not DEFAULT_SPEAKER:
            log.warning(
                "No default_speaker set. Copy one of the entity IDs above "
                "into the addon Configuration tab > default_speaker."
            )
        elif DEFAULT_SPEAKER not in discovered:
            log.warning(
                f"default_speaker '{DEFAULT_SPEAKER}' was not found in the "
                "discovered speaker list — check the entity_id is correct."
            )
    else:
        log.warning(
            "No Music Assistant queue entities discovered. "
            "Is Music Assistant installed and are speakers exposed to HA?"
        )

    # --- Alias map ---
    if ALIAS_MAP:
        log.info(f"Speaker aliases ({len(ALIAS_MAP)}):")
        for alias, eid in ALIAS_MAP.items():
            log.info(f"  '{alias}' -> {eid}")
    else:
        log.info(
            "No speaker aliases configured. Add them under speaker_aliases "
            "in the Configuration tab to route by room name."
        )

    log.info(f"Default speaker: {DEFAULT_SPEAKER or '(not configured)'}")
    mcp.run(transport="sse")
