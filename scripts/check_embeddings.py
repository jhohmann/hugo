"""Manual embedding check without writing sample data to the database.

From the repository root: python scripts/check_embeddings.py
The first run may download the embedding model.
"""

import sys
from pathlib import Path


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.storage.embeddings import embed_document, embed_query

    documents = [
        "Ich plane im April eine Reise nach Japan.",
        "Mein Motorrad benötigt neue Reifen.",
        "Ich möchte mein Haus modernisieren.",
    ]
    query = embed_query("Wann wollte ich nach Tokio reisen?")
    scores = [
        (sum(a * b for a, b in zip(query, embed_document(document), strict=True)), document)
        for document in documents
    ]
    for score, document in sorted(scores, reverse=True):
        print(f"{score:.3f} {document}")


if __name__ == "__main__":
    main()
