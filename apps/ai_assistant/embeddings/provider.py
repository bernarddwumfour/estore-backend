from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from langchain_openai import OpenAIEmbeddings


def get_embedding_model_name() -> str:
    return settings.AI_EMBEDDING_MODEL


def get_embedding_dimensions() -> int:
    return settings.AI_EMBEDDING_DIMENSIONS


def get_embedding_provider() -> OpenAIEmbeddings:
    api_key = getattr(settings, "OPENAI_API_KEY", None)

    if not api_key:
        raise ImproperlyConfigured(
            "OPENAI_API_KEY is not configured."
        )

    return OpenAIEmbeddings(
        model=get_embedding_model_name(),
        dimensions=get_embedding_dimensions(),
        api_key=api_key,
        max_retries=2,
        request_timeout=20,
    )


def validate_embedding(embedding: list[float]) -> list[float]:
    expected = get_embedding_dimensions()

    if len(embedding) != expected:
        raise ValueError(
            f"Embedding dimension mismatch: "
            f"expected {expected}, received {len(embedding)}."
        )

    return embedding


def embed_document(text: str) -> list[float]:
    if not text.strip():
        raise ValueError("Cannot embed empty product text.")

    embedding = get_embedding_provider().embed_documents([text])[0]

    return validate_embedding(embedding)


def embed_query(query: str) -> list[float]:
    if not query.strip():
        raise ValueError("Cannot embed an empty search query.")

    embedding = get_embedding_provider().embed_query(query)

    return validate_embedding(embedding)