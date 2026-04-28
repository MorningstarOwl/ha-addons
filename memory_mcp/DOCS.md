# Memory MCP

A persistent, semantically searchable long-term memory for Home Assistant's
AI assistants. Your assistant can store preferences, facts, people, routines,
and system context — and recall them by meaning, not just by keyword — across
restarts, reboots, and addon updates.

Fully self-contained. No Ollama, no API keys, no external services.
Embeddings run locally inside the addon using ChromaDB's built-in
`all-MiniLM-L6-v2` model.

## Prerequisites

None beyond a working Home Assistant install with the MCP integration.
The addon is supported on `amd64` and `aarch64` (64-bit ARM). 32-bit
architectures are not supported because the ONNX runtime used for
embeddings does not ship 32-bit wheels.

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   and paste `https://github.com/MorningstarOwl/ha-addons`
2. Install **Memory MCP** from the store.
3. Start the addon. The defaults work out of the box; configure only if
   you want to tune the capacity, eviction, or dedup behavior.

The very first start may take a moment while ChromaDB initializes its
on-disk index under `/data/chroma_db`. The ONNX embedding model is already
baked into the Docker image, so the addon is fully offline from the first
boot.

## Required system prompt setup

For the assistant to reliably pull memory context into every conversation,
add this line to your conversation agent's system prompt in Home Assistant:

**Settings → Voice Assistants → (your Assist pipeline) → Conversation agent**

Open the agent's configuration and append to the prompt:

```
At the start of every new conversation, call the load_memory_context tool
to retrieve context about the user before responding to their request.
```

Any capable instruction-following model will call `load_memory_context` on
the first turn of every conversation and use the returned context to
personalize its responses.

## Connecting to Home Assistant

Add the MCP integration in Home Assistant:
**Settings → Devices & Services → Add Integration → Model Context Protocol**

When prompted for the SSE Server URL enter:

```
http://homeassistant.local:8755/sse
```

The integration exposes eight tools:

- `remember` — store a new memory
- `recall` — semantic search over stored memories
- `forget` — delete a memory by ID
- `update_memory` — edit an existing memory
- `list_memories` — browse by recency
- `list_categories` — show how many memories are in each category
- `forget_all` — bulk delete (with confirmation)
- `load_memory_context` — retrieve a curated context block for the assistant

It also declares a `memories://context` MCP resource that future HA
versions may inject automatically once MCP resource support matures.

## Configuration options

| Option | Default | Description |
|---|---|---|
| `owner_name` | `""` | Your name (or the primary user's name). Used in the context block the assistant sees — e.g. `"Here is what I know about Grace:"`. Leave blank for a generic header. |
| `auto_context_limit` | `10` | Number of memories returned by `load_memory_context`. |
| `max_memories` | `2000` | Hard cap on total stored memories. Once hit, the eviction algorithm trims older low-importance memories to make room. |
| `eviction_batch_size` | `10` | Number of memories removed per eviction pass. |
| `eviction_check_interval_seconds` | `3600` | How often the background eviction thread checks the count. Eviction does NOT run on the voice hot path. |
| `dedup_similarity_threshold` | `0.92` | Cosine similarity above which `remember` treats an incoming memory as a duplicate of an existing one and recommends updating instead of creating a new entry. Raise (e.g. 0.97) for stricter dedup that allows more near-duplicates; lower (e.g. 0.85) to aggressively collapse similar memories. |

## Understanding categories and importance

The addon defines seven categories. Your assistant decides which one fits
when it calls `remember`:

- `preference` — how the user likes things done (formatting, tone, units,
  voice vs. text behavior)
- `fact` — objective facts about the user (name, location, family, job)
- `routine` — regular behaviors, schedules, workflows
- `person` — info about specific individuals the user mentions
- `event` — things that happened at a point in time
- `system` — technical facts about the home, network, or infrastructure
- `general` — fallback for memories that don't fit another category

**Importance** (1–5) controls how resistant a memory is to eviction. A
level-5 memory takes ~5× longer to age out than a level-1 memory. Use 5
sparingly, for facts you never want the assistant to lose.

## Managing memory

The assistant should handle memory naturally through conversation:

- **Add:** *"Remember that I prefer weather in Fahrenheit."* →
  assistant calls `remember`.
- **Recall:** The assistant calls `recall` on its own when it notices a
  topic might have stored context.
- **Forget:** *"Forget that you know my work address."* →
  assistant calls `forget` or `forget_all` with the relevant scope.
- **Update:** *"Update the fact about my router — it's on 192.168.2.1
  now."* → assistant calls `update_memory` with the new content.
- **Audit:** *"What do you know about me?"* → assistant calls
  `load_memory_context` or `list_categories`.

## Eviction behavior

When the memory count reaches `max_memories`, a background task
periodically removes the lowest-scoring memories. The score is:

```
days_since_last_access × (6 − importance)
```

So a rarely-accessed importance-1 memory ages out fast; a frequently-used
importance-5 memory is nearly immortal. Every batch removes
`eviction_batch_size` memories (default 10) so the count stays safely
below the cap.

On the very rare case where a burst of `remember` calls pushes the count
above the cap between background checks, the next `remember` call runs
a single synchronous eviction pass to enforce the cap.

## Tuning the dedup threshold

If you're seeing lots of near-duplicate memories ("I like short answers"
and "keep responses brief" stored as two separate entries), lower
`dedup_similarity_threshold` toward 0.85–0.88. If the addon is rejecting
memories that you think are legitimately different, raise it toward
0.95–0.98.

Dedup comparison uses cosine similarity on the local embedding. Similarity
of `1.0` means identical text; `0.0` means completely unrelated.

## Troubleshooting

**"Embedding function mismatch" on startup.** The collection at
`/data/chroma_db` was created with a different embedding configuration
than the server is now running. Revert whatever configuration change
caused this, OR wipe `/data/chroma_db` to re-embed all memories from
scratch (you will lose existing memories).

**ChromaDB startup error / corrupted database.** Stop the addon, remove
`/data/chroma_db/`, and restart. All memories will be lost.

**Dedup rejects every memory.** Your threshold is too low — raise
`dedup_similarity_threshold` toward the default `0.92`.

**Assistant isn't pulling context.** Verify the system-prompt instruction
described above is set. Some smaller models need the instruction worded
more forcefully — try prefixing it with **"CRITICAL:"**.

**Checking the logs.** The addon's logs show memory count at startup,
the embedding function identifier, and every eviction pass. Find them
under **Settings → Add-ons → Memory MCP → Logs**.
