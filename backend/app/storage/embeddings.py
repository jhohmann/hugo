
from functools import lru_cache
from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-small"


@lru_cache(maxsize=1)
def get_model():
    return SentenceTransformer(MODEL_NAME)


def embed_document(text: str):
    return get_model().encode(
        "passage: " + text,
        normalize_embeddings=True
    ).tolist()


def embed_query(text: str):
    return get_model().encode(
        "query: " + text,
        normalize_embeddings=True
    ).tolist()
