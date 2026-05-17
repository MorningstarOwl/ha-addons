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

Phase 1: a single tool (play_music) targeting a hardcoded default speaker
from addon options. Phases 2 and 3 add control_playback, set_volume,
now_playing, list_speakers, and a friendly-name registry with
auto-discovery.

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


# ---------------------------------------------------------------------------
# Home Assistant REST helpers
# ---------------------------------------------------------------------------

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

    If speaker is omitted, plays on the user's default speaker. When
    provided it must be a media_player entity_id, for example
    "media_player.exr1_speaker_media_player_2". Returns a confirmation
    message naming what was played and where.
    """
    q = (query or "").strip()
    if not q:
        return (
            "I need to know what to play. "
            "Tell me an artist, song, album, or genre."
        )

    target = (speaker or "").strip() or DEFAULT_SPEAKER
    if not target:
        return (
            "No speaker is configured. "
            "Please set the default_speaker option in the Music MCP "
            "addon configuration to the entity_id of your Music "
            "Assistant queue entity."
        )

    if not target.startswith("media_player."):
        return (
            f"I cannot play on {target}. "
            "The speaker must be a media_player entity such as "
            "media_player.exr1_speaker_media_player_2."
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
    if not DEFAULT_SPEAKER:
        log.warning(
            "No default_speaker configured. Set it in the addon "
            "Configuration tab before voice playback will work."
        )
    if not SUPERVISOR_TOKEN:
        log.warning(
            "SUPERVISOR_TOKEN not set — HA REST calls will fail. "
            "Is this running outside Supervisor?"
        )

    log.info(f"Starting Music MCP SSE server on port {PORT}...")
    log.info(f"Default speaker: {DEFAULT_SPEAKER or '(not configured)'}")
    mcp.run(transport="sse")
