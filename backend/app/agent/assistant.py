
import json
import logging

from openai import OpenAI

from app.storage.memory_search import (
    search_memories,
    create_memory,
    update_memory,
)

logger = logging.getLogger(__name__)
client = OpenAI()

MODEL = "gpt-5-mini"

SYSTEM_PROMPT = """
Du bist Hugo, ein persönlicher, vorausschauender KI-Assistent.

Du unterstützt den Nutzer bei langfristigen Vorhaben,
Entscheidungen, Zeitplanung und alltäglichen Fragen.

GEDÄCHTNIS
Du verfügst über Werkzeuge für dein Langzeitgedächtnis.

- Suche selbstständig nach Erinnerungen, wenn früherer
  Kontext für die aktuelle Nachricht relevant sein könnte.
- Speichere wichtige persönliche Informationen,
  längerfristige Absichten, Entscheidungen und Fristen.
- Aktualisiere bestehende Erinnerungen, wenn neue
  Informationen sie verändern oder korrigieren.
- Vermeide Duplikate.
- Verändere keine Erinnerung, wenn der Bezug unklar ist.
- Unterscheide Absichten, Überlegungen und Entscheidungen.
- Verwende Erinnerungen natürlich im Gespräch.
- Erwähne interne Speichermechanismen nur auf Nachfrage.

ARBEITSWEISE
- Denke vorausschauend und erkenne Zusammenhänge.
- Nutze Werkzeuge eigenständig, wenn sie sinnvoll sind.
- Erfinde keine Informationen oder Werkzeugergebnisse.
- Externe Aktionen benötigen eine Freigabe des Nutzers.
- Antworte auf Deutsch, sachlich und möglichst knapp.
- Stelle nur notwendige Rückfragen.
"""

TOOLS = [
    {
        "type": "function",
        "name": "search_memories",
        "description": (
            "Durchsucht Hugos langfristiges Gedächtnis "
            "nach relevanten Informationen. "
            "Auch für die Prüfung vor Aktualisierungen verwenden."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_memory",
        "description": (
            "Speichert eine neue langfristig relevante Erinnerung. "
            "Vorher nach möglichen Duplikaten suchen."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "update_memory",
        "description": (
            "Aktualisiert eine bestehende Erinnerung anhand ihrer ID. "
            "Nur verwenden, wenn die Zuordnung eindeutig ist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer"},
                "content": {"type": "string"},
            },
            "required": ["memory_id", "content"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def execute_tool(
    name: str,
    arguments: dict,
    source_message_id: int,
):
    if name == "search_memories":
        limit = max(1, min(arguments["limit"], 10))
        return search_memories(arguments["query"], limit=limit)

    if name == "create_memory":
        memory_id = create_memory(
            arguments["content"],
            source_message_id,
        )
        return {"memory_id": memory_id}

    if name == "update_memory":
        memory_id = arguments["memory_id"]

        # Nur bereits vorhandene, vorgeschlagene
        # Erinnerungen dürfen aktualisiert werden.
        result = update_memory(
            memory_id,
            arguments["content"],
        )

        return {
            "memory_id": memory_id,
            "updated": bool(result),
        }

    raise ValueError(f"Unknown tool: {name}")


def ask_hugo(
    messages: list[dict],
    source_message_id: int,
) -> str:
    conversation = list(messages)

    # Begrenzung der Werkzeugrunden gegen Endlosschleifen.
    for _ in range(8):
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=conversation,
            tools=TOOLS,
            reasoning={"effort": "low"},
            max_output_tokens=1500,
        )

        if response.status == "incomplete":
            raise RuntimeError(
                f"Incomplete AI response: "
                f"{response.incomplete_details}"
            )

        # Die vollständigen Modell-Ausgaben einschließlich
        # Werkzeugaufrufen für die nächste Runde erhalten.
        conversation.extend(
            item.model_dump(exclude_none=True)
            for item in response.output
        )

        tool_calls = [
            item
            for item in response.output
            if item.type == "function_call"
        ]

        if not tool_calls:
            if not response.output_text:
                raise RuntimeError("Empty AI response")

            return response.output_text

        for call in tool_calls:
            try:
                arguments = json.loads(call.arguments)

                logger.info(
                    "Hugo tool: %s %s",
                    call.name,
                    arguments,
                )

                result = execute_tool(
                    call.name,
                    arguments,
                    source_message_id,
                )

            except Exception as exc:
                logger.exception(
                    "Tool execution failed: %s",
                    call.name,
                )
                result = {"error": str(exc)}

            conversation.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(
                    result,
                    ensure_ascii=False,
                    default=str,
                ),
            })

    raise RuntimeError("Maximum tool rounds exceeded")
