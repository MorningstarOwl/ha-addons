# Music MCP

A voice-friendly music playback MCP server backed by Music Assistant.
Your voice assistant gets one opinionated tool for playing music — no
raw media_player entities to choose between, no chance of picking the
Roku TV instead of the speaker you actually meant.

Phase 1 ships a single tool: `play_music`. Phases 2 and 3 will add
playback control (pause, resume, next, previous), volume, "what's
playing," and multi-room support with friendly speaker names and
auto-discovery.

## Prerequisites

- Home Assistant with Music Assistant installed and a music provider
  (e.g. Spotify) configured in Music Assistant.
- At least one Music Assistant queue entity exposed to Home Assistant.
  These have an entity_id ending in `_media_player_2` and carry the
  full feature set (next, previous, queue control).
- The MCP integration installed in Home Assistant.
- A conversation agent with tool-use enabled (Ollama with a model ≥7B
  such as `qwen2.5:7b-instruct`, `llama3.1:8b`, or `hermes3:8b`; or
  any of the cloud LLM agents).

## Installation

1. Add this repository to Home Assistant if you have not already:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   and paste `https://github.com/MorningstarOwl/ha-addons`
2. Install **Music MCP** from the store.
3. On the **Configuration** tab, set `default_speaker` to the
   entity_id of the Music Assistant queue entity you want to be the
   default playback target. **This must be the `_2` entity** — the
   queue overlay, not the base LVA entity:
   ```
   media_player.exr1_speaker_media_player_2
   ```
4. Save, then **Start** the addon.
5. The Log tab should show:
   ```
   INFO: Starting Music MCP SSE server on port 8767...
   INFO: Default speaker: media_player.exr1_speaker_media_player_2
   ```

## Connecting to Home Assistant

Add the MCP integration in Home Assistant:
**Settings → Devices & Services → Add Integration → Model Context Protocol**

When prompted for the SSE Server URL enter:

```
http://homeassistant.local:8767/sse
```

After a moment the integration will discover the tool:

- `play_music` — search for and start playing music on a speaker

## Required system prompt setup

Most local LLMs need a nudge to reach for the playback tool when asked
to play music, rather than trying to call raw `media_player.*` services
themselves. Add this line to your conversation agent's system prompt:

**Settings → Voice Assistants → (your Assist pipeline) → Conversation agent**

Open the agent's configuration and append:

```
When the user asks to play music, call the play_music tool with their
request as the query. Do not call media_player services directly.
```

For multi-speaker households, also tell the agent which speaker is
local to which voice assistant. For example, on the EXR1 satellite:

```
You are the assistant in the office. If the user does not specify a
speaker when asking to play music, do not pass a speaker argument —
the tool will use the default speaker.
```

## Configuration options

| Option | Default | Description |
|---|---|---|
| `default_speaker` | `""` | The entity_id of the Music Assistant queue entity to use when no speaker is specified. Must end in `_2` — the `_2` suffix marks the MA queue overlay, which supports next/previous and full queue control. The base LVA entity (without `_2`) does not. |
| `speaker_aliases` | `[]` | A list of `{name, entity_id}` pairs that let the voice assistant refer to speakers by a short friendly name instead of a full entity_id. See **Speaker aliases** below. |

### Finding the right entity_id

When the addon starts it queries Home Assistant and logs every Music
Assistant queue entity it finds:

```
INFO: Discovered 2 Music Assistant speaker(s):
INFO:   1. media_player.exr1_speaker_media_player_2
INFO:   2. media_player.kitchen_speaker_media_player_2
```

Open **Settings → Add-ons → Music MCP → Log** right after starting the
addon and copy the entity_id you want into `default_speaker`.

### Speaker aliases

Aliases let you map a short name to a speaker entity_id so the voice
assistant can say "play X in the kitchen" and the addon routes it
correctly without the LLM needing to know entity_ids.

Example configuration:

```yaml
speaker_aliases:
  - name: office
    entity_id: media_player.exr1_speaker_media_player_2
  - name: kitchen
    entity_id: media_player.kitchen_speaker_media_player_2
```

The `name` field is case-insensitive. The `entity_id` must be the full
`media_player.*_2` entity, same as `default_speaker`.

### Per-satellite system prompt (routing by room)

To make each voice satellite automatically play on the speaker in its
room, add one line to that satellite's pipeline system prompt:

**Settings → Voice Assistants → (your pipeline) → Conversation agent**

```
When asked to play music and the user does not specify a room, use speaker "office".
```

Replace `"office"` with the alias name for the room that satellite lives
in. When the user *does* name a room ("play X in the kitchen"), the LLM
will pass `speaker="kitchen"` and the alias map routes it to the right
entity automatically.

## What `play_music` does

The tool calls `music_assistant.play_media` on the configured speaker
with `enqueue: play` (which replaces any current queue). Music Assistant
treats the `query` argument as a free-form search string and picks the
best match across its configured providers.

Example assistant exchanges:

- *"Play Joanna Newsom."* → `play_music(query="Joanna Newsom")` →
  "Playing Joanna Newsom on exr1 speaker."
- *"Put on some lo-fi beats."* → `play_music(query="lo-fi beats")` →
  "Playing lo-fi beats on exr1 speaker."
- *"Play the album Ys."* → `play_music(query="Ys album")` →
  "Playing Ys album on exr1 speaker."

## Troubleshooting

**Addon log shows `play_media failed: HTTP 500`.**
The `default_speaker` is probably the base LVA entity (no `_2` suffix)
instead of the queue entity. The base entity does not advertise the
features Music Assistant needs for queue-based playback. Switch
`default_speaker` to the `_2` variant.

**Addon log shows `play_media failed: HTTP 400 ... entity not found`.**
The entity_id is wrong. Check **Developer Tools → States** in Home
Assistant for the correct entity_id of your Music Assistant queue
overlay.

**Tool calls reach the addon but Music Assistant does not play
anything.** Try the same call manually from Developer Tools → Actions:
```yaml
action: music_assistant.play_media
data:
  entity_id: media_player.exr1_speaker_media_player_2
  media_id: "Joanna Newsom"
  enqueue: play
```
If that does not play either, the issue is in Music Assistant or its
Spotify connection, not in this addon.

**Assistant tries to play music on the wrong device anyway.**
Confirm that the conversation agent's system prompt includes the
`play_music` instruction above. Some smaller models also need the
raw `media_player` entities un-exposed to Assist (Settings → Voice
Assistants → Expose) so they cannot be picked at all. Once Phase 2
ships, the per-room defaults will reduce the need for this.

**Checking the logs.** Every tool call is logged at INFO level. Find
them under **Settings → Add-ons → Music MCP → Logs**.
