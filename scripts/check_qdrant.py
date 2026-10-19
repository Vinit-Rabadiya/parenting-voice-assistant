# checks cloud access using backend settings and prints the collection count.
from urllib.parse import urlsplit

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from backend.core.config import settings


def main() -> None:
    # read the values already loaded from the root .env by backend/core/config.py.
    url = (settings.QDRANT_URL or "").strip()
    api_key = (settings.QDRANT_API_KEY or "").strip()
    if not url or not api_key:
        raise SystemExit("Set QDRANT_URL and QDRANT_API_KEY in the root .env.")

    # use the secure cluster endpoint, not the dashboard page or a url containing credentials.
    try:
        endpoint = urlsplit(url)
        valid = (
            endpoint.scheme == "https" and bool(endpoint.hostname)
            and endpoint.username is None and endpoint.password is None
            and endpoint.path in ("", "/") and not endpoint.query and not endpoint.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise SystemExit("QDRANT_URL must be the HTTPS cluster endpoint without a dashboard path.")

    client = None
    try:
        # configure the connection; timeout bounds the wait for a server response.
        client = QdrantClient(url=url, port=443, api_key=api_key, timeout=15)
        # this read-only request returns collection information without uploading data.
        result = client.get_collections()
        print("Qdrant connection successful.")
        print(f"Collections available: {len(result.collections)}")
        # inspect the collection before uploading passage vectors.
        collection = client.get_collection("caregiver_guidance_minilm_v1")
        print("Vector configuration:", collection.config.params.vectors)
        print("Stored points:", collection.points_count)
    except UnexpectedResponse as exc:
        # show the status without printing server response content or credentials.
        raise SystemExit(f"Qdrant returned HTTP {exc.status_code}. Check endpoint and key permissions.") from None
    except ResponseHandlingException:
        raise SystemExit("Could not reach Qdrant. Check the network, endpoint, and cluster status.") from None
    except (ValueError, OSError):
        raise SystemExit("Could not initialize the Qdrant connection. Check the local settings.") from None
    finally:
        # release network resources after success or failure.
        if client is not None:
            client.close()


# module execution lets python resolve backend imports from the repository root.
if __name__ == "__main__":
    main()
