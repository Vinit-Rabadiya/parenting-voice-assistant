"""Own-account administrator review records; never read from the coaching path."""

from datetime import datetime, timezone
from uuid import uuid4

from firebase_admin import firestore

from backend.schemas.feedback_improvements import ImprovementRecord


CASE_FIELDS = frozenset({"title", "category", "scenario", "expected_behavior", "fictional_confirmed",
                         "fictional_date_of_birth", "evaluation_date", "status"})


class ImprovementNotFound(Exception):
    pass


class ImprovementConflict(Exception):
    pass


class ImprovementStageError(Exception):
    pass


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
        data = {"version": 1, "content": content.model_dump(mode="json", include=CASE_FIELDS),
                "created_at": now, "updated_at": now, "released_at": None}
        document.create(data, timeout=10)
        return ImprovementRecord.model_validate({"id": document.id, **data})

    def update(self, uid, identifier, expected_version, content):
        if content.status != "investigating":
            raise ImprovementStageError("Feedback cases support saving investigation notes only.")
        document = self.collection(uid).document(identifier)

        @firestore.transactional
        def save(transaction):
            snapshot = document.get(transaction=transaction)
            if not snapshot.exists:
                raise ImprovementNotFound()
            previous = self.record(snapshot)
            if previous.version != expected_version:
                raise ImprovementConflict()
            if previous.content.status != "investigating":
                raise ImprovementStageError("Archived feedback cases are read-only.")
            proposed = previous.content.model_dump(mode="json", exclude={"release_without_evaluation"})
            proposed.update(content.model_dump(mode="json", include=CASE_FIELDS))
            now = datetime.now(timezone.utc)
            data = {"version": previous.version + 1, "content": proposed,
                    "created_at": previous.created_at, "updated_at": now, "released_at": previous.released_at}
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
