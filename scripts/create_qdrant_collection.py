# creates the collection used to store our caregiver passage vectors.
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from backend.core.config import settings


def main() -> None:
    if not settings.QDRANT_URL or not settings.QDRANT_API_KEY:
        raise SystemExit("Set the Qdrant connection values in the root .env.")

    collection_name = "caregiver_guidance_minilm_v1"

    client = QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        timeout=15,
    )

    try:
        # leave an existing collection intact when this command is run again.
        if client.collection_exists(collection_name):
            print("Collection already exists; no changes made.")
            return

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=384,
                distance=Distance.COSINE,
            ),
        )
        print(f"Created collection: {collection_name}")
    finally:
        client.close()


if __name__ == "__main__":
    main()