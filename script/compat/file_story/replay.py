"""Pure v4 narrative-state validation and reduction."""
import copy
import re


KNOWLEDGE_KINDS = {"observed", "told", "inferred", "believed", "suspected", "false-belief"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
FORBIDDEN_KEYS = {
    "affection", "affection_score", "anger_score", "攻略", "攻略进度",
    "love", "love_score", "romance_stage", "trust", "trust_score",
    "好感度", "信任值", "愤怒值", "嫉妒值",
}


class StateError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def safe_id(value, field="id"):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value):
        raise StateError("INVALID_ID", "{} must be a safe ID".format(field))
    return value


def forbidden_key(value, trail=""):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
            if normalized in FORBIDDEN_KEYS:
                return "{}.{}".format(trail, key).strip(".")
            found = forbidden_key(child, "{}.{}".format(trail, key).strip("."))
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = forbidden_key(child, "{}[{}]".format(trail, index))
            if found:
                return found
    return None


def merge_dict(base, patch):
    result = copy.deepcopy(base or {})
    for key, value in patch.items():
        if key == "id":
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def initial_state(story, node_id="node-root", baseline=None):
    baseline = copy.deepcopy(baseline or {})
    return {
        "version": 4,
        "story_id": story["id"],
        "node_id": node_id,
        "canon_revision_id": story.get("default_canon_revision_id", "canon-v1"),
        "scene": baseline.get("scene"),
        "world_facts": baseline.get("world_facts", {}),
        "characters": baseline.get("characters", {}),
        "relationships": baseline.get("relationships", {}),
        "character_memories": baseline.get("character_memories", []),
        "historical_traces": baseline.get("historical_traces", {}),
        "open_threads": baseline.get("open_threads", {}),
        "director": baseline.get("director", {"story_phase": "opening", "needs_review": False}),
        "author_notes": baseline.get("author_notes", ""),
        "recent_path_summaries": baseline.get("recent_path_summaries", []),
    }


def _items(delta, key):
    value = delta.get(key, [])
    if not isinstance(value, list):
        raise StateError("INVALID_DELTA", "{} must be an array".format(key))
    return value


def apply_delta(base, delta, node_id):
    if not isinstance(delta, dict):
        raise StateError("INVALID_DELTA", "delta must be an object")
    found = forbidden_key(delta)
    if found:
        raise StateError("FORBIDDEN_CHARACTER_STATE", "Numeric/攻略-style state is forbidden at {}".format(found))
    result = copy.deepcopy(base)
    story_id = result["story_id"]
    facts = result["world_facts"]
    additions = list(_items(delta, "facts_add"))
    supersessions = list(_items(delta, "facts_supersede"))
    for replacement in _items(delta, "facts_replace"):
        old_id = safe_id(replacement.get("id"), "replaced fact id")
        new_fact = replacement.get("new_fact")
        if not isinstance(new_fact, dict) or not replacement.get("reason"):
            raise StateError("INVALID_FACT_REPLACEMENT", "Replacement needs new_fact and reason")
        additions.append(copy.deepcopy(new_fact))
        supersessions.append({"id": old_id, "reason": replacement["reason"],
                              "superseded_by": new_fact.get("id")})
    for fact in additions:
        fact_id = safe_id(fact.get("id"), "fact id")
        claim = fact.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            raise StateError("INVALID_FACT", "Fact claim is required")
        if fact.get("kind") == "user-directive" and not fact.get("source"):
            raise StateError("INVALID_FACT", "A user-directive fact requires an explicit source")
        if fact_id in facts:
            if facts[fact_id].get("status") == "active" and facts[fact_id].get("claim") == claim:
                continue
            raise StateError("DUPLICATE_FACT", "Fact ID already exists: {}".format(fact_id))
        stored = copy.deepcopy(fact)
        stored.update({"id": fact_id, "claim": claim.strip(), "status": "active", "source_node_id": node_id})
        facts[fact_id] = stored
    for item in supersessions:
        fact_id = safe_id(item.get("id"), "superseded fact id")
        if fact_id not in facts or facts[fact_id].get("status") != "active":
            raise StateError("INVALID_FACT_SUPERSESSION", "Active fact not found: {}".format(fact_id))
        facts[fact_id]["status"] = "superseded"
        facts[fact_id]["superseded_at_node_id"] = node_id
        if item.get("reason"):
            facts[fact_id]["superseded_reason"] = str(item["reason"])
        if item.get("superseded_by"):
            successor_id = safe_id(item["superseded_by"], "superseded_by")
            if successor_id not in facts or facts[successor_id].get("status") != "active":
                raise StateError("INVALID_FACT_SUPERSESSION", "Successor fact is not active: {}".format(successor_id))
            facts[fact_id]["superseded_by"] = successor_id

    characters = result["characters"]
    for patch in _items(delta, "character_upserts"):
        character_id = safe_id(patch.get("id"), "character id")
        characters[character_id] = merge_dict(characters.get(character_id, {}), patch)
        characters[character_id]["id"] = character_id
        characters[character_id]["updated_at_node_id"] = node_id

    for memory in _items(delta, "memories_add"):
        character_id = safe_id(memory.get("character_id"), "memory character_id")
        if character_id != "player" and character_id not in characters:
            raise StateError("UNKNOWN_CHARACTER", "Memory refers to unknown character")
        kind = memory.get("kind")
        if kind not in KNOWLEDGE_KINDS:
            raise StateError("INVALID_MEMORY", "Unsupported memory kind")
        if not memory.get("claim") or not memory.get("source"):
            raise StateError("INVALID_MEMORY", "Memory claim and source are required")
        confidence = memory.get("confidence")
        if confidence is not None and confidence not in CONFIDENCE_LEVELS:
            raise StateError("INVALID_MEMORY", "Invalid memory confidence")
        stored = copy.deepcopy(memory)
        stored.setdefault("id", "memory-{}-{}".format(node_id, len(result["character_memories"]) + 1))
        safe_id(stored["id"], "memory id")
        if any(item.get("id") == stored["id"] for item in result["character_memories"]):
            raise StateError("DUPLICATE_MEMORY", "Memory already exists: {}".format(stored["id"]))
        stored.update({"source_node_id": node_id, "learned_at_node_id": node_id})
        result["character_memories"].append(stored)

    traces = result["historical_traces"]
    for trace in _items(delta, "historical_traces_add"):
        trace_id = safe_id(trace.get("id"), "historical trace id")
        if trace_id in traces:
            raise StateError("DUPLICATE_TRACE", "Trace already exists: {}".format(trace_id))
        if not trace.get("text"):
            raise StateError("INVALID_TRACE", "Trace text is required")
        stored = copy.deepcopy(trace)
        stored.update({"id": trace_id, "status": "active", "source_node_id": node_id})
        traces[trace_id] = stored
    for patch in _items(delta, "historical_traces_update"):
        trace_id = safe_id(patch.get("id"), "historical trace id")
        if trace_id not in traces:
            raise StateError("UNKNOWN_TRACE", "Trace not found: {}".format(trace_id))
        traces[trace_id] = merge_dict(traces[trace_id], patch)
        traces[trace_id]["id"] = trace_id
        traces[trace_id]["updated_at_node_id"] = node_id
    for trace_id in _items(delta, "historical_traces_close"):
        trace_id = safe_id(trace_id, "historical trace id")
        if trace_id not in traces:
            raise StateError("UNKNOWN_TRACE", "Trace not found: {}".format(trace_id))
        traces[trace_id].update(status="closed", closed_at_node_id=node_id)

    threads = result["open_threads"]
    for thread in _items(delta, "threads_open"):
        thread_id = safe_id(thread.get("id"), "thread id")
        if not thread.get("text"):
            raise StateError("INVALID_THREAD", "Thread text is required")
        if thread_id in threads and threads[thread_id].get("status") == "open":
            raise StateError("DUPLICATE_THREAD", "Thread is already open: {}".format(thread_id))
        stored = copy.deepcopy(thread)
        stored.update({"id": thread_id, "status": "open", "opened_at_node_id": node_id})
        threads[thread_id] = stored
    for patch in _items(delta, "threads_update"):
        thread_id = safe_id(patch.get("id"), "thread id")
        if thread_id not in threads:
            raise StateError("UNKNOWN_THREAD", "Thread not found: {}".format(thread_id))
        threads[thread_id] = merge_dict(threads[thread_id], patch)
        threads[thread_id]["id"] = thread_id
    for thread_id in _items(delta, "threads_close"):
        thread_id = safe_id(thread_id, "thread id")
        if thread_id not in threads:
            raise StateError("UNKNOWN_THREAD", "Thread not found: {}".format(thread_id))
        threads[thread_id].update(status="closed", closed_at_node_id=node_id)

    if "relationships" in delta:
        if not isinstance(delta["relationships"], dict):
            raise StateError("INVALID_DELTA", "relationships must be an object")
        result["relationships"] = merge_dict(result["relationships"], delta["relationships"])
    if "scene" in delta:
        if not isinstance(delta["scene"], dict):
            raise StateError("INVALID_SCENE", "scene must be an object")
        for field in ("time", "location", "summary"):
            if not isinstance(delta["scene"].get(field), str) or not delta["scene"][field].strip():
                raise StateError("INVALID_SCENE", "scene.{} is required".format(field))
        result["scene"] = copy.deepcopy(delta["scene"])
        result["scene"].setdefault("participants", [])
        result["scene"]["index"] = delta["scene"].get("index", result.get("scene", {}).get("index", 0))
    if "director_update" in delta:
        result["director"] = merge_dict(result["director"], delta["director_update"])
    if "author_notes" in delta:
        if not isinstance(delta["author_notes"], str):
            raise StateError("INVALID_DELTA", "author_notes must be a string")
        result["author_notes"] = delta["author_notes"]

    if result.get("scene"):
        result["recent_path_summaries"] = (result["recent_path_summaries"] + [{
            "node_id": node_id,
            "summary": result["scene"]["summary"],
        }])[-8:]
    result.update(version=4, story_id=story_id, node_id=node_id)
    return result
