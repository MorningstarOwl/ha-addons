# Music MCP

An MCP server that lets a voice assistant play music from a **local** library
through Music Assistant. It searches the library, plays what it actually found,
and says so in plain English.

## What this is for, and what it is not for

This add-on is the **fallback** path, not the main road.

If your house answers "play Rumours" with a Home Assistant sentence trigger
that calls `music_assistant.search` and `music_assistant.play_media` directly,
that path is faster than any LLM can be — a few hundred milliseconds, no model
in the loop — and you should keep it. What a sentence trigger cannot do is
handle a request that does not name a thing: *"put on something mellow"*,
*"something like the Cure"*, *"that album with the prism on it"*. Answering
those needs a model that can look at what is in the library and choose. That is
what this add-on is for.

Scope it accordingly. Two tools, both aimed at open-ended requests:

| Tool | What it does |
|---|---|
| `search_library` | Read-only. Reports what names actually exist in the library. |
| `play_music` | Searches, ranks, plays the resolved item, names what it found. |

There is deliberately no pause, next, volume or "what's playing" tool. Those
utterances are short, unambiguous and constant, which makes them exactly the
wrong thing to spend an LLM round trip on; handle them with local sentence
triggers.

## The library is local, and that changes the tool descriptions

This matters more than anything else in the add-on, so it is worth being blunt
about. Music Assistant's search against a **filesystem** provider is substring
matching over an index of your own files. It is not fuzzy, not semantic, and
not connected to any streaming catalogue. So a model that has been told "Music
Assistant will search Spotify" — which is what version 0.1 told it — forms
streaming-shaped queries, and those fail in two ways:

- *"lo-fi study beats playlist"* matches nothing at all.
- *"jazz radio"* matches an album called **"Marian McPartland's Piano Jazz
  Radio Broadcast With Steely Dan"**, and the house plays Steely Dan.

The second failure is the dangerous one, because it looks like success. The
tool docstrings in this add-on therefore state that the library is local files,
that matching is substring-only, and that open-ended requests must go through
`search_library` first. If you point this add-on at a Spotify-backed Music
Assistant instead, the docstrings are the thing to revise.

## Prerequisites

- Home Assistant with the **Music Assistant** add-on installed, a music
  provider configured, and its library indexed.
- The **Music Assistant integration** set up in Home Assistant, so that the
  `music_assistant.*` services exist and at least one Music Assistant player is
  exposed to Home Assistant. This is a separate step from installing the add-on,
  and without it every call here fails.
- The **Model Context Protocol** integration in Home Assistant.
- A conversation agent with tool use. A model of 7B or more handles two tools
  reliably; smaller ones tend to skip `search_library` and guess.

### Which entity is the speaker

Music Assistant creates its own `media_player` entity per player, and that is
the one to aim at. The base player — the ESPHome satellite, the Chromecast, the
DLNA renderer — generally cannot queue, skip or shuffle, because those are
server-side operations that Music Assistant performs on its behalf.

Older versions of this document told you to look for an entity id ending in
`_media_player_2`. **That advice was wrong**, and it is worth explaining why,
because the mistake is easy to repeat. The `_2` suffix is not Music Assistant's
doing; it is Home Assistant appending a counter when two entities would
otherwise slugify to the same id. Music Assistant names its player from mDNS,
so on an install where the base player is called `Kitchen Speaker` and Music
Assistant calls its own `kitchen-speaker`, the two do not collide and there is
no `_2` anywhere. Discovery keyed on that suffix finds nothing.

You do not have to work this out by hand. The add-on asks Home Assistant which
entities the `music_assistant` integration owns, and logs them at startup:

```
INFO: Discovered 1 Music Assistant player(s):
INFO:   1. media_player.home_assistant_voice_0994d0
INFO: Default speaker: media_player.home_assistant_voice_0994d0
INFO: Music Assistant config entry: 01M3QQW2V0QX088F67J52N6C1D
```

If there is exactly one player, that is the default and you need configure
nothing at all.

## Installation

1. Add this repository to Home Assistant if you have not already:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, and paste
   `https://github.com/MorningstarOwl/ha-addons`
2. Install **Music MCP**, then **Start** it.
3. Read the **Log** tab. If it found your player and named a config entry, you
   are done. If you have more than one player, set `default_speaker` on the
   **Configuration** tab to the one you want, and add aliases (below).
4. Add the MCP integration: **Settings → Devices & Services → Add Integration
   → Model Context Protocol**, with the SSE Server URL
   `http://homeassistant.local:8767/sse`

## Configuration options

| Option | Default | Description |
|---|---|---|
| `default_speaker` | `""` | Entity id of the Music Assistant player to use when the assistant does not name a room. Optional: when the integration exposes exactly one player, the add-on uses it and logs that it did. Set this when there is more than one. |
| `speaker_aliases` | `[]` | `{name, entity_id}` pairs mapping a room name to a player, so the assistant can route by room without knowing entity ids. |

A `default_speaker` that is not one of the discovered players is **not** fatal.
If there is exactly one real player, the add-on uses it and warns:

```
WARNING: default_speaker 'media_player.exr1_speaker_media_player_2' is not a
Music Assistant player in this install; using the only one there is,
media_player.home_assistant_voice_0994d0. Update the Configuration tab to
silence this.
```

That behaviour exists because a stale `default_speaker` copied from someone
else's setup is the single most likely way to install this add-on and have
nothing work.

### Speaker aliases

```yaml
speaker_aliases:
  - name: master bedroom
    entity_id: media_player.home_assistant_voice_0994d0
  - name: kitchen
    entity_id: media_player.kitchen_media_player
```

`name` is matched case-insensitively. Aliases do double duty: they are how the
assistant names a room on the way in, and how the add-on names it on the way
out. With an alias configured the confirmation reads *"Playing Rumours in the
master bedroom."*; without one it falls back to the entity's area, then to its
friendly name, which for an mDNS-named player is *"Playing Rumours on
home-assistant-voice-0994d0."* — true, but not something you want read aloud.

Only alias rooms that really have a speaker. Asking for a room with no alias
gets an honest *"I do not know a speaker called kitchen"*, which is a better
answer than music starting in the wrong room.

### Per-satellite system prompt (routing by room)

To make each satellite default to the speaker in its own room, add one line to
that pipeline's conversation-agent prompt:

```
When asked to play music and the user does not specify a room, use speaker "master bedroom".
```

## What the tools do

### `search_library(query, kind="", limit=8)`

Calls `music_assistant.search` and returns matching names grouped by sort:

```
Artists: Fleetwood Mac
Albums: Fleetwood Mac; Peter Green's Fleetwood Mac by Fleetwood Mac; The Very Best Of Fleetwood Mac [CD1] by Fleetwood Mac
Tracks: Albatross by Fleetwood Mac; Affairs Of The Heart by Fleetwood Mac
```

Nothing plays. `kind` narrows to one of `artist`, `album`, `track`, `playlist`.

### `play_music(query, speaker="", kind="", similar=False)`

1. `music_assistant.search` for `query`.
2. Rank the hits: exact name matches first across every sort, then artists,
   albums, playlists, tracks. A bare artist name should mean "play this
   artist", not "play one of their songs", and an album title should not lose
   to a track that merely contains the same word.
3. `music_assistant.play_media` with the resolved `library://…` uri and
   `enqueue: play`, which replaces the current queue.
4. Return what was found, not what was asked for.

Version 0.1 skipped steps 1, 2 and 4: it passed the raw query straight to
`play_media` as `media_id` and echoed the query back as confirmation. That
reports success whether or not anything resolved, and gives the model no way to
learn that its query was wrong.

`similar=True` adds `radio_mode`, which plays the match and then continues with
similar music **from the same local library**. It is the honest answer to
"something like X" — but only when X is itself in the library, so pair it with
`search_library`.

Example exchanges:

- *"Play Rumours."* → `play_music(query="Rumours")` →
  "Playing Rumours by Fleetwood Mac in the master bedroom."
- *"Play the album Fleetwood Mac."* → `play_music(query="Fleetwood Mac",
  kind="album")` → "Playing Fleetwood Mac in the master bedroom."
- *"Put on something like Fleetwood Mac."* → `search_library(query="Fleetwood
  Mac")`, then `play_music(query="Fleetwood Mac", similar=True)` → "Playing
  Fleetwood Mac and similar music after it in the master bedroom."
- *"Play some Portishead."* → `play_music(query="Portishead")` → "I could not
  find Portishead in the music library. It is a local collection, so if it is
  not on the NAS I cannot play it."

## Testing

`test_server.py` exercises the module against a real Home Assistant. It is an
integration test on purpose: nearly every claim in this add-on is a claim about
how Music Assistant actually behaves, and a mocked backend would only confirm
what the author already assumed. It intercepts `music_assistant.play_media`, so
running it plays nothing.

```
HASS_URL=http://homeassistant.local:8123 HASS_TOKEN=<long-lived token> \
    python3 test_server.py
```

## Notes for anyone changing this

- **`mcp` is pinned below 2.x in the Dockerfile.** SDK 2.0 renamed `FastMCP` to
  `mcp.server.mcpserver.MCPServer` and removed `mcp.server.fastmcp`. The
  dependency used to be unpinned, which meant the next rebuild of the image
  after that release would have produced an add-on that crashed on import —
  and a version bump forces a rebuild. Migrating to the 2.x API is a job for
  every add-on in this repository at once, not for this one alone.
- **`music_assistant.search` takes `limit` at the top level.** The service
  description in Music Assistant 2.10.4 advertises a nested
  `search_options: {limit, library_only}` object; sending that form is rejected
  with HTTP 400. Measured, not assumed.
- **Service responses need `?return_response=true`** on the REST call, or the
  search result comes back empty.
- **`radio` is the one search-result key that is not pluralised.** The mapping
  from `media_type` to result key is explicit in `RESULT_KEY` for that reason.

## Troubleshooting

**Log says `No Music Assistant players discovered`.** The Music Assistant
*integration* is not set up, or no player has "Expose to Home Assistant" set.
Installing the Music Assistant add-on alone is not enough. Check that
`music_assistant.play_media` appears under **Developer Tools → Actions**.

**Log says `Music Assistant config entry: (not found)`.** Same cause. The
add-on needs the integration's config entry id to call its services, and
discovers it from the speaker entity.

**Every play attempt answers "I could not find …".** The search is working and
the library genuinely does not contain the query. Try `search_library` with a
shorter fragment. If the library was only just added to Music Assistant, its
scan may still be running.

**Playback returns "I found X but could not start playback".** The search
resolved but `play_media` was refused. The usual cause is aiming at the base
player rather than the Music Assistant one; the service requires an entity
advertising `PLAY_MEDIA`, and Music Assistant's target selector filters on it.

**The assistant plays something absurd.** It sent a mood or genre as the query
and substring matching found a coincidence. Confirm the agent is seeing the
current tool descriptions — an MCP client caches them, so reload the Model
Context Protocol integration after upgrading this add-on.

**The assistant plays raw `media_player` entities instead of using the tool.**
Un-expose those entities from Assist (**Settings → Voice Assistants → Expose**)
so they cannot be chosen.

**Checking the logs.** Every tool call is logged at INFO, including the uri it
resolved to: **Settings → Add-ons → Music MCP → Logs**.
