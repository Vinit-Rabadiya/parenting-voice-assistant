# Creates the collection used to store caregiver passage vectors.
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from backend.core.config import settings


def ensure_age_indexes(client: QdrantClient, collection_name: str) -> None:
    """Index the original numeric age fields without rewriting stored passages."""
    for field in ("min_days", "max_days_exclusive", "min_months", "max_months_exclusive"):
        client.create_payload_index(
            collection_name=collection_name,
            field_name=f"source_age.{field}",
            field_schema=PayloadSchemaType.INTEGER,
            wait=True,
        )


def main() -> None:
    if not settings.QDRANT_URL or not settings.QDRANT_API_KEY:
        raise SystemExit("Set the Qdrant connection values in the root .env.")

    collection_name = settings.QDRANT_COLLECTION

    client = QdrantClient(
        url=settings.QDRANT_URL,
        port=443,
        api_key=settings.QDRANT_API_KEY,
        timeout=15,
    )

    try:
        # leave an existing collection intact when this command is run again.
        if client.collection_exists(collection_name):
            ensure_age_indexes(client, collection_name)
            print("Collection preserved; age payload indexes ensured.")
            return

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=384,
                distance=Distance.COSINE,
            ),
        )
        ensure_age_indexes(client, collection_name)
        print(f"Created collection: {collection_name}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
