"""Own-account administrator review records; never read from the coaching path."""

from datetime import datetime, timezone
from uuid import uuid4

from firebase_admin import firestore

from backend.schemas.feedback_improvements import ImprovementChecks, ImprovementRecord


class ImprovementNotFound(Exception):
    pass


class ImprovementConflict(Exception):
    pass


class ImprovementStageError(Exception):
    pass


def persisted_content(content):
    fields = content.model_dump(mode="json")
    if not content.release_without_evaluation:
        fields.pop("release_without_evaluation")
    return fields


def updated_content(current, proposed):
    """A recorded evaluation must be reopened before its reviewed content changes."""
    allowed = {
        "investigating": {"investigating", "ready_for_release"},
        "ready_for_release": {"investigating", "ready_for_release", "released"},
        "released": {"investigating", "released"},
    }
    direct_release = current.status == "investigating" and proposed.status == "released" and proposed.release_without_evaluation
    if proposed.status not in allowed[current.status] and not direct_release:
        raise ImprovementStageError("Record a successful evaluation before recording a release.")
    if current.status == proposed.status == "released" and current != proposed:
        raise ImprovementStageError("Reopen the case before changing a recorded release.")
    if current.status != "investigating" and proposed.status != "investigating":
        exclude = {"status", "release_revision", "deployment_checked", "release_notes"}
        if current.model_dump(exclude=exclude) != proposed.model_dump(exclude=exclude):
            raise ImprovementStageError("Reopen the case before changing reviewed content.")
    if current.status != "investigating" and proposed.status == "investigating":
        proposed = proposed.model_copy(update={"checks": ImprovementChecks(), "release_revision": "",
                                               "deployment_checked": False, "release_notes": "", "release_without_evaluation": False})
    return proposed


class FeedbackImprovementService:
    def __init__(self, client):
        self.client = client

    def collection(self, uid):
        # Existing account-data recursive deletion also removes these records.
        return self.client.collection("users").document(uid).collection("feedback_improvements")

    @staticmethod
    def record(snapshot):
        return ImprovementRecord.model_validate({**snapshot.to_dict(), "id": snapshot.id})

    def list(self, uid, limit=20, before=None):
        collection = self.collection(uid)
        query = collection.order_by("updated_at", direction=firestore.Query.DESCENDING)
        if before:
            cursor = collection.document(before).get(timeout=5)
            if not cursor.exists:
                raise ImprovementNotFound()
            query = query.start_after(cursor)
        records = [self.record(snapshot) for snapshot in query.limit(limit + 1).stream(timeout=10)]
        return {"items": records[:limit], "next_cursor": records[limit - 1].id if len(records) > limit else None}

    def create(self, uid, content):
        if content.status != "investigating":
            raise ImprovementStageError("New cases must begin with investigation.")
        document = self.collection(uid).document(uuid4().hex)
        now = datetime.now(timezone.utc)
        data = {"version": 1, "content": persisted_content(content),
                "created_at": now, "updated_at": now, "released_at": None}
        document.create(data, timeout=10)
        return ImprovementRecord.model_validate({"id": document.id, **data})

    def update(self, uid, identifier, expected_version, content):
        document = self.collection(uid).document(identifier)

        @firestore.transactional
        def save(transaction):
            snapshot = document.get(transaction=transaction)
            if not snapshot.exists:
                raise ImprovementNotFound()
            previous = self.record(snapshot)
            if previous.version != expected_version:
                raise ImprovementConflict()
            proposed = updated_content(previous.content, content)
            now = datetime.now(timezone.utc)
            released = (previous.released_at or now) if proposed.status == "released" else None
            data = {"version": previous.version + 1, "content": persisted_content(proposed),
                    "created_at": previous.created_at, "updated_at": now, "released_at": released}
            transaction.set(document, data)
            return ImprovementRecord.model_validate({"id": identifier, **data})

        return save(self.client.transaction())

    def delete(self, uid, identifier, expected_version):
        document = self.collection(uid).document(identifier)

        @firestore.transactional
        def remove(transaction):
            snapshot = document.get(transaction=transaction)
            if not snapshot.exists:
                raise ImprovementNotFound()
            if self.record(snapshot).version != expected_version:
                raise ImprovementConflict()
            transaction.delete(document)

        remove(self.client.transaction())
