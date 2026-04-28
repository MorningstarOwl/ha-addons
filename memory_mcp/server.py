"""
Memory MCP Server
-----------------
Persistent, semantically-searchable long-term memory for Home Assistant's
AI assistants. Reads options from /data/options.json (injected by HA
Supervisor), stores memories in a ChromaDB collection at /data/chroma_db,
and exposes eight tools plus one resource over an MCP SSE endpoint.

Embeddings are generated locally via ChromaDB's built-in
DefaultEmbeddingFunction (all-MiniLM-L6-v2 via ONNX runtime). No Ollama,
no API keys, no external services.

MCP SSE endpoint: http://homeassistant.local:8755/sse
"""

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone

# Silence ChromaDB's anonymous telemetry at the earliest possible point,
# in case the Dockerfile's ENV is overridden for any reason.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from mcp.server.fastmcp import FastMCP

# Belt-and-suspenders telemetry kill-switch. ChromaDB 0.5.x has a bug where
# a handful of telemetry events fire during client startup BEFORE the
# Settings(anonymized_telemetry=False) flag is honored, and the bundled
# posthog client's capture() signature has drifted from what chromadb
# calls — surfacing as harmless but noisy ERROR lines like:
#     "capture() takes 1 positional argument but 3 were given"
# We replace Posthog.capture with a no-op so those events silently vanish
# instead of cluttering the logs. Wrapped in try/except so a future
# chromadb refactor that moves or renames this class will not crash startup.
try:
    from chromadb.telemetry.product.posthog import Posthog as _ChromaPosthog
    _ChromaPosthog.capture = lambda *_a, **_kw: None
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPTIONS_FILE = "/data/options.json"
DATA_PATH = "/data/chroma_db"
COLLECTION_NAME = "memories"
# Identifier stamped into collection metadata on first creation so we can
# detect an embedding-model / distance-metric change across restarts.
EMBEDDING_FN_ID = "chromadb:DefaultEmbeddingFunction:all-MiniLM-L6-v2:cosine"
PORT = 8755

VALID_CATEGORIES = {
    "preference", "fact", "routine", "person", "event", "system", "general",
}


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
OWNER_NAME: str = (options.get("owner_name") or "").strip()
AUTO_CONTEXT_LIMIT: int = int(options.get("auto_context_limit", 10))
MAX_MEMORIES: int = int(options.get("max_memories", 2000))
EVICTION_BATCH_SIZE: int = int(options.get("eviction_batch_size", 10))
EVICTION_INTERVAL: int = int(options.get("eviction_check_interval_seconds", 3600))
DEDUP_THRESHOLD: float = float(options.get("dedup_similarity_threshold", 0.92))


# ---------------------------------------------------------------------------
# ChromaDB initialization
# ---------------------------------------------------------------------------

# A reentrant lock serializes all ChromaDB access. FastMCP dispatches
# tool calls on a thread pool, and the background eviction thread also
# touches the collection — without this lock we would race on SQLite.
_chroma_lock = threading.RLock()

_embedding_fn = DefaultEmbeddingFunction()


def _init_collection():
    """Open (or create) the memories collection and verify compatibility."""
    # Settings-based telemetry suppression — the ANONYMIZED_TELEMETRY env var
    # is honored inconsistently across chromadb minor versions, but the
    # Settings-passed value is always respected.
    client = chromadb.PersistentClient(
        path=DATA_PATH,
        settings=Settings(anonymized_telemetry=False),
    )

    # hnsw:space is set at create-time to cosine. all-MiniLM embeddings are
    # not unit-normalized, so cosine is the correct similarity metric.
    col = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_embedding_fn,
        metadata={
            "embedding_fn_id": EMBEDDING_FN_ID,
            "hnsw:space": "cosine",
        },
    )

    meta = dict(col.metadata or {})
    stamp = meta.get("embedding_fn_id")

    if stamp is None:
        # Either brand new (stamp should have been written on create above)
        # or an older pre-stamp collection being migrated forward. Stamp it
        # now. Chroma rejects modify() if hnsw:* keys are present, even when
        # the values are unchanged — strip those before updating.
        sanitized = {k: v for k, v in meta.items() if not k.startswith("hnsw:")}
        sanitized["embedding_fn_id"] = EMBEDDING_FN_ID
        try:
            col.modify(metadata=sanitized)
            log.info(f"Stamped collection with embedding_fn_id={EMBEDDING_FN_ID}")
        except Exception as e:
            log.warning(f"Could not stamp collection metadata: {e}")
    elif stamp != EMBEDDING_FN_ID:
        log.error(
            f"Embedding function mismatch. Collection was created with "
            f"'{stamp}' but the server is configured for '{EMBEDDING_FN_ID}'. "
            f"Either revert the server configuration, or wipe {DATA_PATH} "
            f"to re-embed all memories from scratch."
        )
        raise SystemExit(1)

    return col


try:
    collection = _init_collection()
except SystemExit:
    raise
except Exception as e:
    log.exception(f"Failed to initialize ChromaDB at {DATA_PATH}: {e}")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id(uid: str) -> str:
    return uid[:8] if uid else uid


def _days_since(iso_str: str) -> float:
    if not iso_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)


def _tags_to_json(tags) -> str:
    if tags is None:
        return "[]"
    try:
        return json.dumps(list(tags))
    except Exception:
        return "[]"


def _build_where(category=None, min_importance=None):
    """Compose a Chroma where-filter from optional category and min_importance."""
    conds = []
    if category:
        conds.append({"category": {"$eq": str(category)}})
    if min_importance is not None:
        conds.append({"importance": {"$gte": int(min_importance)}})
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return {"$and": conds}


def _resolve_memory_id(memory_id: str):
    """Accept a full UUID or a unique prefix; return the full UUID or None.

    Raises ValueError if the prefix matches more than one memory.
    """
    if not memory_id:
        return None
    memory_id = memory_id.strip()

    # Exact match first
    try:
        exact = collection.get(ids=[memory_id], include=[])
        if exact and memory_id in (exact.get("ids") or []):
            return memory_id
    except Exception:
        pass

    # Prefix search — Chroma has no prefix filter, so pull all ids
    try:
        all_data = collection.get(include=[])
    except Exception:
        return None
    all_ids = all_data.get("ids") or []
    matches = [i for i in all_ids if i.startswith(memory_id)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"Memory ID '{memory_id}' is ambiguous — {len(matches)} memories "
            f"start with that prefix. Please use more characters."
        )
    return None


# ---------------------------------------------------------------------------
# Eviction
# ---------------------------------------------------------------------------

def _eviction_score(meta: dict) -> float:
    last = meta.get("last_accessed_at") or meta.get("created_at") or _now_iso()
    days = _days_since(last)
    imp = int(meta.get("importance", 3))
    imp = max(1, min(5, imp))
    return days * (6 - imp)


def _run_eviction_pass(force: bool = False) -> int:
    """
    Evict up to EVICTION_BATCH_SIZE memories if the count is at or above
    MAX_MEMORIES. If force=True, evict regardless of count (used on the
    emergency inline path when remember has just pushed us over the cap).
    """
    with _chroma_lock:
        try:
            count = collection.count()
        except Exception as e:
            log.warning(f"Eviction skipped — could not count collection: {e}")
            return 0

        if count < MAX_MEMORIES and not force:
            return 0

        try:
            all_data = collection.get(include=["metadatas"])
        except Exception as e:
            log.warning(f"Eviction skipped — could not fetch collection: {e}")
            return 0

        ids = all_data.get("ids") or []
        metas = all_data.get("metadatas") or []
        if not ids:
            return 0

        scored = []
        for rid, meta in zip(ids, metas):
            scored.append((rid, _eviction_score(meta or {})))
        scored.sort(key=lambda t: t[1], reverse=True)

        victims = [rid for rid, _ in scored[:EVICTION_BATCH_SIZE]]
        if not victims:
            return 0

        try:
            collection.delete(ids=victims)
        except Exception as e:
            log.warning(f"Eviction delete failed: {e}")
            return 0

        log.info(
            f"Evicted {len(victims)} memories (count was {count}, cap {MAX_MEMORIES})"
        )
        return len(victims)


def _eviction_worker():
    """Periodic background eviction check."""
    while True:
        time.sleep(EVICTION_INTERVAL)
        try:
            _run_eviction_pass()
        except Exception as e:
            log.warning(f"Background eviction pass failed: {e}")


# ---------------------------------------------------------------------------
# Shared context builder (used by load_memory_context tool AND the
# memories://context resource, so the two cannot drift apart)
# ---------------------------------------------------------------------------

def _build_context_block(topic: str = "") -> str:
    limit = max(1, int(AUTO_CONTEXT_LIMIT))
    with _chroma_lock:
        try:
            count = collection.count()
        except Exception:
            count = 0
        if count == 0:
            return "There are no stored memories yet."

        topic = (topic or "").strip()

        if topic:
            # Unified score: 0.6 * similarity + 0.4 * normalized importance.
            # Fetch a generous candidate set so the importance weight can
            # meaningfully re-rank against pure similarity.
            candidate_n = min(count, max(limit * 3, 20))
            try:
                results = collection.query(
                    query_texts=[topic],
                    n_results=candidate_n,
                    include=["metadatas", "documents", "distances"],
                )
            except Exception as e:
                log.warning(f"Context query failed, falling back to importance sort: {e}")
                results = None

            if results and results.get("ids") and results["ids"][0]:
                ids = results["ids"][0]
                docs = results["documents"][0] if results.get("documents") else []
                metas = results["metadatas"][0] if results.get("metadatas") else []
                dists = results["distances"][0] if results.get("distances") else []

                scored = []
                for rid, doc, meta, dist in zip(ids, docs, metas, dists):
                    sim = max(0.0, min(1.0, 1.0 - float(dist)))
                    imp = int((meta or {}).get("importance", 3))
                    norm_imp = (max(1, min(5, imp)) - 1) / 4.0  # -> 0..1
                    score = 0.6 * sim + 0.4 * norm_imp
                    scored.append((score, rid, doc, meta))
                scored.sort(key=lambda t: t[0], reverse=True)
                selected = [(rid, doc, meta) for _s, rid, doc, meta in scored[:limit]]
            else:
                selected = []

            if selected:
                return _format_context(selected)
            # Fall through to no-topic branch if query produced nothing

        # No topic (or topic branch fell through): sort by importance desc,
        # then last_accessed_at desc.
        try:
            data = collection.get(include=["metadatas", "documents"])
        except Exception as e:
            log.warning(f"Context fetch failed: {e}")
            return "Could not load memory context."

        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        records = list(zip(ids, docs, metas))
        records.sort(
            key=lambda t: (
                int((t[2] or {}).get("importance", 3)),
                (t[2] or {}).get("last_accessed_at")
                or (t[2] or {}).get("created_at")
                or "",
            ),
            reverse=True,
        )
        selected = records[:limit]

        if not selected:
            return "There are no stored memories yet."
        return _format_context(selected)


def _format_context(selected) -> str:
    owner = OWNER_NAME or "the user"
    lines = [f"Here is what I know about {owner}:"]
    for _rid, doc, _meta in selected:
        text = (doc or "").strip()
        if not text:
            continue
        if not text.endswith((".", "!", "?")):
            text += "."
        lines.append(text)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("Memory MCP Server", host="0.0.0.0", port=PORT)


# ---- remember --------------------------------------------------------------

@mcp.tool()
def remember(
    content: str,
    category: str = "general",
    tags: list[str] | None = None,
    importance: int = 3,
    source: str = "assistant",
) -> str:
    """
    Store a new long-term memory about the user.

    Use this whenever the user shares something that should persist across
    conversations: a preference, a fact about themselves or their environment,
    a person they mention, a routine, or a notable event.

    Before storing, this tool runs a similarity check. If a near-identical
    memory already exists, it returns that memory's ID and recommends calling
    update_memory instead of creating a duplicate.

    Args:
        content: The memory text. Write it as a clear, self-contained statement
            that will still make sense months from now.
        category: One of preference, fact, routine, person, event, system, general.
        tags: Optional free-form labels for additional filtering.
        importance: 1 (trivial) to 5 (critical). Defaults to 3.
        source: Who is storing this — usually "assistant" or "user".
    """
    try:
        content = (content or "").strip()
        if not content:
            return "Cannot store an empty memory."

        try:
            importance = int(importance)
        except Exception:
            importance = 3
        importance = max(1, min(5, importance))

        category = (category or "general").strip() or "general"
        source = (source or "assistant").strip() or "assistant"

        with _chroma_lock:
            # Dedup check
            try:
                existing_count = collection.count()
            except Exception:
                existing_count = 0

            if existing_count > 0:
                try:
                    res = collection.query(
                        query_texts=[content],
                        n_results=1,
                        include=["distances", "documents"],
                    )
                    if res.get("ids") and res["ids"][0]:
                        top_id = res["ids"][0][0]
                        top_doc = (res["documents"][0][0] or "") if res.get("documents") else ""
                        top_dist = float(res["distances"][0][0]) if res.get("distances") else 1.0
                        similarity = max(0.0, min(1.0, 1.0 - top_dist))
                        if similarity >= DEDUP_THRESHOLD:
                            preview = top_doc[:80]
                            return (
                                f"A very similar memory already exists. ID: {_short_id(top_id)}. "
                                f"Existing content: '{preview}'. "
                                f"Consider updating that memory instead of creating a new one."
                            )
                except Exception as e:
                    log.warning(f"Dedup check failed (continuing with store): {e}")

            # Store
            memory_id = str(uuid.uuid4())
            now = _now_iso()
            meta = {
                "category": category,
                "tags": _tags_to_json(tags),
                "importance": importance,
                "source": source,
                "created_at": now,
                "updated_at": now,
                "last_accessed_at": now,
                "access_count": 0,
            }
            collection.add(ids=[memory_id], documents=[content], metadatas=[meta])

            # Emergency inline eviction only when we're already over the cap
            try:
                if collection.count() > MAX_MEMORIES:
                    _run_eviction_pass(force=True)
            except Exception as e:
                log.warning(f"Post-write eviction check failed: {e}")

        return (
            f"Memory stored. ID: {_short_id(memory_id)}. "
            f"Stored under category '{category}' with importance {importance}."
        )
    except Exception as e:
        log.exception("remember failed")
        return f"Could not store memory: {e}"


# ---- recall ---------------------------------------------------------------

@mcp.tool()
def recall(
    query: str,
    category: str = "",
    limit: int = 5,
    min_importance: int = 0,
) -> str:
    """
    Retrieve memories relevant to a natural-language query using semantic
    search. Returns a numbered list with content, category, importance, and
    a short ID for each result.

    Accessed memories have their last_accessed_at and access_count metadata
    refreshed so the eviction algorithm preserves memories the user actively
    uses.

    Args:
        query: Natural language description of what to find.
        category: Optional category filter (preference, fact, routine,
            person, event, system, general).
        limit: Maximum number of results (default 5).
        min_importance: Optional minimum importance (1-5); pass 0 for no filter.
    """
    try:
        query = (query or "").strip()
        if not query:
            return "Cannot recall — no query provided."

        try:
            limit = int(limit)
        except Exception:
            limit = 5
        limit = max(1, min(50, limit))

        cat_filter = (category or "").strip() or None
        try:
            min_imp = int(min_importance)
        except Exception:
            min_imp = 0
        imp_filter = min_imp if min_imp > 0 else None
        where = _build_where(category=cat_filter, min_importance=imp_filter)

        with _chroma_lock:
            kwargs = {
                "query_texts": [query],
                "n_results": limit,
                "include": ["metadatas", "documents", "distances"],
            }
            if where:
                kwargs["where"] = where

            results = collection.query(**kwargs)
            ids = results["ids"][0] if results.get("ids") and results["ids"] else []
            docs = results["documents"][0] if results.get("documents") else []
            metas = results["metadatas"][0] if results.get("metadatas") else []

            if not ids:
                return "No memories matched that query."

            # Update access tracking
            now = _now_iso()
            updated_metas = []
            for meta in metas:
                m = dict(meta or {})
                m["last_accessed_at"] = now
                m["access_count"] = int(m.get("access_count", 0)) + 1
                updated_metas.append(m)
            try:
                collection.update(ids=ids, metadatas=updated_metas)
            except Exception as e:
                log.warning(f"Failed to refresh access metadata: {e}")

        lines = []
        for i, (rid, doc, meta) in enumerate(zip(ids, docs, metas), start=1):
            m = meta or {}
            cat = m.get("category", "general")
            imp = m.get("importance", 3)
            lines.append(
                f"{i}. {doc} (category: {cat}, importance: {imp}, ID: {_short_id(rid)})"
            )
        return "\n".join(lines)
    except Exception as e:
        log.exception("recall failed")
        return f"Could not recall memories: {e}"


# ---- forget ---------------------------------------------------------------

@mcp.tool()
def forget(memory_id: str) -> str:
    """
    Delete a single memory by ID. Accepts either a full UUID or a unique
    short prefix such as the 8-character ID returned by recall.

    Args:
        memory_id: Full UUID or unique prefix of the memory to delete.
    """
    try:
        memory_id = (memory_id or "").strip()
        if not memory_id:
            return "Cannot delete — no memory ID provided."
        with _chroma_lock:
            full = _resolve_memory_id(memory_id)
            if full is None:
                return f"No memory found with ID {memory_id}."
            collection.delete(ids=[full])
            return f"Memory {_short_id(full)} has been deleted."
    except ValueError as e:
        return str(e)
    except Exception as e:
        log.exception("forget failed")
        return f"Could not delete memory: {e}"


# ---- update_memory --------------------------------------------------------

@mcp.tool()
def update_memory(
    memory_id: str,
    content: str = "",
    category: str = "",
    tags: list[str] | None = None,
    importance: int = 0,
) -> str:
    """
    Edit the content or metadata of an existing memory. Only the fields you
    supply are changed; everything else is preserved. Providing new content
    re-embeds the memory so future semantic searches reflect the new text.

    Args:
        memory_id: UUID or unique short prefix of the memory to update.
        content: New memory text (triggers re-embedding).
        category: New category value.
        tags: Replacement tag list (passing [] clears all tags).
        importance: New importance (1-5); pass 0 to leave unchanged.
    """
    try:
        memory_id = (memory_id or "").strip()
        if not memory_id:
            return "Cannot update — no memory ID provided."

        content = (content or "").strip()
        category = (category or "").strip()
        try:
            importance = int(importance)
        except Exception:
            importance = 0

        changed = bool(content) or bool(category) or tags is not None or importance > 0
        if not changed:
            return (
                "Nothing to update — provide at least one of content, "
                "category, tags, or importance."
            )

        with _chroma_lock:
            full = _resolve_memory_id(memory_id)
            if full is None:
                return f"No memory found with ID {memory_id}."

            existing = collection.get(
                ids=[full], include=["metadatas", "documents"]
            )
            if not existing.get("ids"):
                return f"No memory found with ID {memory_id}."

            meta = dict((existing.get("metadatas") or [{}])[0] or {})
            docs = existing.get("documents") or [""]
            new_doc = docs[0] if docs else ""

            if content:
                new_doc = content
            if category:
                meta["category"] = category
            if tags is not None:
                meta["tags"] = _tags_to_json(tags)
            if importance and 1 <= importance <= 5:
                meta["importance"] = importance
            meta["updated_at"] = _now_iso()

            collection.update(ids=[full], documents=[new_doc], metadatas=[meta])

        return f"Memory {_short_id(full)} updated."
    except ValueError as e:
        return str(e)
    except Exception as e:
        log.exception("update_memory failed")
        return f"Could not update memory: {e}"


# ---- list_memories --------------------------------------------------------

@mcp.tool()
def list_memories(
    category: str = "",
    limit: int = 20,
    min_importance: int = 0,
) -> str:
    """
    Browse stored memories by recency, without a semantic query.

    Results are sorted by creation time, newest first. Browsing does NOT
    update last_accessed_at — that only happens through recall.

    Args:
        category: Optional category filter.
        limit: Maximum number of results (default 20).
        min_importance: Optional minimum importance (1-5); pass 0 for no filter.
    """
    try:
        try:
            limit = int(limit)
        except Exception:
            limit = 20
        limit = max(1, min(200, limit))

        cat_filter = (category or "").strip() or None
        try:
            min_imp = int(min_importance)
        except Exception:
            min_imp = 0
        imp_filter = min_imp if min_imp > 0 else None
        where = _build_where(category=cat_filter, min_importance=imp_filter)

        with _chroma_lock:
            kwargs = {"include": ["metadatas", "documents"]}
            if where:
                kwargs["where"] = where
            data = collection.get(**kwargs)

        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []

        records = list(zip(ids, docs, metas))
        # Chroma has no native metadata sort — order in Python
        records.sort(
            key=lambda t: (t[2] or {}).get("created_at", ""),
            reverse=True,
        )
        records = records[:limit]

        if not records:
            return "No memories stored."

        lines = []
        for i, (rid, doc, meta) in enumerate(records, start=1):
            m = meta or {}
            cat = m.get("category", "general")
            imp = m.get("importance", 3)
            text = (doc or "")
            preview = text[:100] + ("..." if len(text) > 100 else "")
            lines.append(
                f"{i}. {preview} (category: {cat}, importance: {imp}, ID: {_short_id(rid)})"
            )
        return "\n".join(lines)
    except Exception as e:
        log.exception("list_memories failed")
        return f"Could not list memories: {e}"


# ---- list_categories ------------------------------------------------------

@mcp.tool()
def list_categories() -> str:
    """
    Return a summary of how many memories are in each category, and the
    total. Useful for understanding the shape of memory before deciding
    where to search or store.
    """
    try:
        with _chroma_lock:
            data = collection.get(include=["metadatas"])
        metas = data.get("metadatas") or []
        total = len(metas)
        if total == 0:
            return "You have no memories stored yet."

        counts: dict[str, int] = {}
        for m in metas:
            cat = ((m or {}).get("category") or "general").strip() or "general"
            counts[cat] = counts.get(cat, 0) + 1

        parts = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        summary = ", ".join(f"{cat} ({n})" for cat, n in parts)
        return f"You have {total} memories total. Categories: {summary}."
    except Exception as e:
        log.exception("list_categories failed")
        return f"Could not list categories: {e}"


# ---- forget_all -----------------------------------------------------------

@mcp.tool()
def forget_all(confirm: bool = False, category: str = "") -> str:
    """
    Bulk delete memories. DANGEROUS — requires confirm=true to proceed.

    If a category is provided, only memories in that category are deleted.
    Without a category, ALL memories are deleted.

    Args:
        confirm: Must be explicitly true to perform deletion.
        category: Optional — restrict deletion to this category.
    """
    try:
        if not confirm:
            return "Confirmation required. Pass confirm=true to delete memories."

        category = (category or "").strip()
        with _chroma_lock:
            if category:
                data = collection.get(
                    where={"category": {"$eq": category}},
                    include=[],
                )
                ids = data.get("ids") or []
                if not ids:
                    return f"No memories to delete in category '{category}'."
                collection.delete(ids=ids)
                return f"Deleted {len(ids)} memories from category '{category}'."
            else:
                data = collection.get(include=[])
                ids = data.get("ids") or []
                if not ids:
                    return "No memories to delete."
                collection.delete(ids=ids)
                return f"Deleted all {len(ids)} memories."
    except Exception as e:
        log.exception("forget_all failed")
        return f"Could not delete memories: {e}"


# ---- load_memory_context --------------------------------------------------

@mcp.tool()
def load_memory_context(topic: str = "") -> str:
    """
    Return a curated context block of the most relevant memories about the
    user, formatted as a clean TTS-friendly paragraph.

    CALL THIS AT THE START OF EVERY NEW CONVERSATION so you know what you
    already know about the user before responding to their request.

    Args:
        topic: Optional — bias retrieval toward memories relevant to this
            topic. Leave blank to return the highest-importance memories
            regardless of subject.
    """
    try:
        return _build_context_block(topic=topic)
    except Exception as e:
        log.exception("load_memory_context failed")
        return f"Could not load memory context: {e}"


# ---- memories://context resource ------------------------------------------

@mcp.resource("memories://context")
def memories_context_resource() -> str:
    """Curated context block of key memories about the user. Produces the
    same content as the load_memory_context tool — shares a backing function
    so the two cannot drift apart."""
    try:
        return _build_context_block()
    except Exception as e:
        log.exception("memories://context resource failed")
        return f"Could not load memory context: {e}"


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _start_background_eviction():
    t = threading.Thread(
        target=_eviction_worker,
        name="memory-eviction",
        daemon=True,
    )
    t.start()
    log.info(
        f"Background eviction thread started (interval {EVICTION_INTERVAL}s, "
        f"batch {EVICTION_BATCH_SIZE}, cap {MAX_MEMORIES})"
    )


if __name__ == "__main__":
    try:
        initial_count = collection.count()
    except Exception:
        initial_count = -1

    log.info(f"Starting Memory MCP SSE server on port {PORT}...")
    log.info(f"Data path: {DATA_PATH}")
    log.info(f"Embedding function: {EMBEDDING_FN_ID}")
    log.info(f"Memory count at startup: {initial_count}")
    if OWNER_NAME:
        log.info(f"Owner name: {OWNER_NAME}")

    # One eviction pass at startup if we're already over the cap
    try:
        _run_eviction_pass()
    except Exception as e:
        log.warning(f"Startup eviction pass failed: {e}")

    _start_background_eviction()

    mcp.run(transport="sse")
