"""Public Kenya contacts shared by the emergency pop-up and urgent responses."""

import json
from pathlib import Path

CONTACTS_PATH = Path(__file__).resolve().parents[2] / "shared" / "kenya-contacts.json"
_CONTACTS = json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))


def emergency_resources(country: str | None, *, include_hospitals: bool = False) -> tuple[dict, ...]:
    """Return independent records without inferring a nearby hospital or live availability."""
    if country != "KE":
        return ()
    return tuple(dict(contact) for contact in _CONTACTS
                 if include_hospitals or contact["category"] != "hospital")
