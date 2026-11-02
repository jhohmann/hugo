
from app.storage.memory_search import (
    add_memory,
    search_memories,
)

add_memory("Ich plane im April eine Reise nach Japan.")
add_memory("Mein Motorrad benötigt neue Reifen.")
add_memory("Ich möchte mein Haus modernisieren.")

results = search_memories(
    "Wann wollte ich nach Tokio reisen?"
)

for result in results:
    print(
        result["similarity"],
        result["content"]
    )
