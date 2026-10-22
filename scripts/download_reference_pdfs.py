"""Download original reference PDFs only; never save website HTML."""
import hashlib
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = (
    ("Birth-to-five-2025.pdf", "https://www.publichealth.hscni.net/sites/default/files/2025-04/Birth%20to%20five%202025.pdf"),
    ("Kenya-community-health-guidelines-2024.pdf", "https://www.health.go.ke/sites/default/files/2025-04/Clinical%20Guidelines%20for%20Level%201%20Community%20Health%20Services.pdf"),
)
MAX_BYTES = 30 * 1024 * 1024


def describe(raw: bytes) -> tuple[int, str]:
    if not raw.startswith(b"%PDF-") or len(raw) > MAX_BYTES:
        raise ValueError("Response is not a supported-size PDF; nothing was saved.")
    reader = PdfReader(BytesIO(raw))
    if reader.is_encrypted or not reader.pages:
        raise ValueError("PDF is encrypted or empty.")
    return len(reader.pages), hashlib.sha256(raw).hexdigest()


def main():
    output = ROOT / "data/raw/pdfs"
    output.mkdir(parents=True, exist_ok=True)
    for filename, url in REFERENCES:
        target = output / filename
        if target.exists():
            raw = target.read_bytes()
        else:
            with urlopen(Request(url, headers={"User-Agent": "CaregiverReferenceReview/1.0"}), timeout=30) as response:
                if not response.geturl().startswith("https://"):
                    raise ValueError("PDF download redirected away from HTTPS.")
                raw = response.read(MAX_BYTES + 1)
            describe(raw)
            target.write_bytes(raw)
        pages, digest = describe(raw)
        print(f"{filename}: pages={pages} sha256={digest}")
        print(f"Source: {url}")


if __name__ == "__main__":
    main()
