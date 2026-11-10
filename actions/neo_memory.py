"""
actions/neo_memory.py — Tri-Tier Lifelong Memory & Knowledge Graph Action for NEO.

Auto-discovered by core/action_loader.py. Exposes lifelong memory, entity knowledge
graph traversal, and episodic recalls to Gemini Live and the Assistant.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from core.neo_brain import brain

_BASE_DIR = Path(__file__).resolve().parent.parent


def manage_neo_memory(parameters: dict, **kwargs) -> str:
    """Handler for NEO Lifelong Tri-Tier Memory operations."""
    operation = str(parameters.get("operation", "query")).strip().lower()
    query = str(parameters.get("query", "")).strip()
    entity = str(parameters.get("entity", "")).strip()
    relation = str(parameters.get("relation", "")).strip().upper()
    target = str(parameters.get("target", "")).strip()
    category = str(parameters.get("category", "GENERAL")).strip().upper()

    if operation == "remember":
        if not entity or not target:
            return "Error: Both 'entity' and 'target' are required to remember a fact."
        rel = relation or "RELATED_TO"
        brain.graph.upsert_entity(entity, entity_type=category)
        brain.graph.upsert_entity(target, entity_type="ATTRIBUTE")
        brain.graph.add_relation(entity, target, rel, context=f"Direct memory update: {entity} {rel} {target}")
        brain.episodic.log_event("MEMORY_RECORDED", f"Learned fact: {entity} {rel} {target}")
        return f"Successfully saved to Lifelong Knowledge Graph: ({entity}) ──[{rel}]──> ({target})"

    elif operation == "get_context":
        summary = brain.working.get_summary()
        return (
            f"Active Window: {summary.get('active_window') or 'None'}\n"
            f"Clipboard Snippet: {summary.get('clipboard_snippet') or 'Empty'}\n"
            f"Current Goal: {summary.get('current_goal') or 'None'}\n"
            f"Recent Turn Count: {summary.get('turn_count', 0)}"
        )

    else:  # "query"
        if not query:
            return "Error: 'query' parameter is required to search memory."

        # 1. Search Knowledge Graph
        graph_matches = brain.graph.search_entities(query, limit=3)
        graph_facts = []
        for em in graph_matches:
            rels = brain.graph.get_related_entities(em["name"])
            for r in rels:
                graph_facts.append(f"• {em['name']} {r['relation_type']} {r['target_name']}")

        # 2. Search Episodic Timeline
        episodic_matches = brain.episodic.query_events(query, limit=3)
        episodic_facts = [
            f"• [{e['event_type']}]: {e['content']}"
            for e in episodic_matches
        ]

        out = []
        if graph_facts:
            out.append("Knowledge Graph Relations:\n" + "\n".join(graph_facts))
        if episodic_facts:
            out.append("Episodic Event Recalls:\n" + "\n".join(episodic_facts))

        if not out:
            return f"No memories found matching '{query}' in Lifelong Memory."
        return "\n\n".join(out)


TOOL = {
    "name": "manage_neo_memory",
    "description": (
        "Queries, retrieves, or updates NEO's Tri-Tier Lifelong Memory and Semantic Knowledge Graph. "
        "Use 'operation'='query' to recall past conversations, preferences, projects, or technical facts. "
        "Use 'operation'='remember' to permanently save user facts, preferences, or project relations. "
        "Use 'operation'='get_context' to read active desktop focus and clipboard snippet."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "One of: 'query' (search memory), 'remember' (save new fact), or 'get_context' (inspect working memory).",
            },
            "query": {
                "type": "STRING",
                "description": "Topic, person, technology, or question to search for in memory.",
            },
            "entity": {
                "type": "STRING",
                "description": "Subject entity for 'remember' (e.g. 'user', 'NEO', 'Project Mark-LVI').",
            },
            "relation": {
                "type": "STRING",
                "description": "Predicate relation for 'remember' (e.g. 'PREFERS', 'USES', 'WORKING_ON', 'OWNS').",
            },
            "target": {
                "type": "STRING",
                "description": "Target entity or property value for 'remember' (e.g. 'Dark Mode', 'Python 3.13').",
            },
            "category": {
                "type": "STRING",
                "description": "Entity category (e.g. 'PERSON', 'PROJECT', 'TECHNOLOGY', 'PREFERENCE').",
            },
        },
        "required": ["operation"],
    },
    "handler": manage_neo_memory,
}
