"""Firestore access scoped to one authenticated caregiver at a time."""

from datetime import date, datetime, timezone
from uuid import uuid4

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from backend.services.age import age_details, current_date, within_project_scope
from backend.schemas.children import ChildHealthDetails
from backend.core.privacy import FEEDBACK_CONSENT_VERSIONS
from backend.services.profile_context import health_context_available

BASELINE_MILESTONES = (
    (2, ["Social smile and follows a colourful object"]),
    (4, ["Holds the head upright", "Responds to sound and familiar voices"]),
    (6, ["Rolls over", "Reaches for and grasps objects", "Babbles"]),
    (9, ["Sits without support", "Transfers objects between hands"]),
    (12, ["Takes steps with support", "Uses simple gestures", "Says 2 to 3 words"]),
    (18, ["Walks without support", "Drinks from a cup", "Points to body parts on request"]),
    (25, ["Kicks a ball", "Builds a tower with blocks", "Uses short sentences"]),
)


def calculate_age(date_of_birth: date, today: date | None = None, *, enforce_scope: bool = True) -> tuple[int, float, str]:
    """Calculate the display age on the server; clients never supply it as authority."""
    today = today or current_date()
    age_days, completed_months, calendar_months = age_details(date_of_birth, today)
    if enforce_scope and not within_project_scope(date_of_birth, today):
        raise ValueError("Coaching supports children from birth through their second birthday.")
    age_months = round(calendar_months, 1)
    if completed_months == 0:
        age_label = f"{age_days} day{'s' if age_days != 1 else ''}"
    else:
        age_label = f"{age_months:g} months"
    return age_days, age_months, age_label


def baseline_milestones(age_months: float) -> list[str]:
    """Return the reviewed milestone band closest to the child's calculated age."""
    for upper_month in BASELINE_MILESTONES:
        if age_months < upper_month[0]:
            return upper_month[1]
    return BASELINE_MILESTONES[-1][1]


class CaregiverDataService:
    """Persist only the data needed for the authenticated caregiver's experience."""

    def __init__(self, client=None):
        self.client = client or firestore.client()

    def _account(self, uid: str):
        return self.client.collection("users").document(uid)

    @staticmethod
    def _active(snapshot) -> bool:
        return snapshot.exists and not (snapshot.to_dict() or {}).get("deleting", False)

    def _children(self, uid: str):
        return self.client.collection("users").document(uid).collection("children")

    def get_consent(self, uid: str) -> dict:
        document = self.client.collection("users").document(uid).get()
        return (document.to_dict() or {}) if self._active(document) else {}

    def save_consent(self, uid: str, version: str) -> datetime:
        document = self.client.collection("users").document(uid)

        @firestore.transactional
        def accept(transaction):
            snapshot = document.get(transaction=transaction)
            data = (snapshot.to_dict() or {}) if snapshot.exists else {}
            if data.get("deleting", False):
                raise ValueError("Account data is being deleted. Please retry after deletion finishes.")
            if (data.get("consent_version") == version and data.get("consent_at") is not None
                    and data.get("caregiver_authority") is True):
                return data["consent_at"]
            accepted_at = datetime.now(timezone.utc)
            values = {"consent_version": version, "consent_at": accepted_at, "caregiver_authority": True}
            feedback_at = data.get("feedback_consent_at", data.get("consent_at"))
            if (data.get("consent_version") in FEEDBACK_CONSENT_VERSIONS
                    and data.get("caregiver_authority") is True
                    and isinstance(feedback_at, datetime) and feedback_at.utcoffset() is not None):
                values["feedback_consent_at"] = feedback_at
            else:
                # Reset stale permission when the previous notice did not authorize sharing.
                values["feedback_consent_at"] = accepted_at
            transaction.set(document, values, merge=True)
            return accepted_at

        return accept(self.client.transaction())

    def _interactions(self, uid: str):
        return self.client.collection("users").document(uid).collection("interactions")

    def _conversations(self, uid: str):
        return self.client.collection("users").document(uid).collection("conversations")

    def _transaction_documents(self, transaction, references: list, fields: tuple[str, ...]):
        """Read related owned documents in one RPC, within the same transaction."""
        return self._documents(references, fields=fields, transaction=transaction)

    def _documents(self, references: list, *, fields=None, transaction=None):
        expected = {reference.path for reference in references}
        snapshots = {}
        # BatchGet replies are unordered. Missing documents have exists=False;
        # an incomplete/foreign/duplicate reply is an availability failure.
        for snapshot in self.client.get_all(references, field_paths=fields, transaction=transaction):
            path = snapshot.reference.path
            if path not in expected or path in snapshots:
                raise RuntimeError("Invalid transaction document response.")
            snapshots[path] = snapshot
        if set(snapshots) != expected:
            raise RuntimeError("Incomplete transaction document response.")
        return tuple(snapshots[reference.path] for reference in references)

    def get_coaching_documents(self, uid: str, child_id: str, conversation_id: str | None) -> dict:
        """One fresh account-scoped read for consent, profile and optional parent."""
        references = [self.client.collection("users").document(uid), self._children(uid).document(child_id)]
        if conversation_id is not None:
            references.append(self._conversations(uid).document(conversation_id))
        documents = self._documents(references)
        return {"consent": (documents[0].to_dict() or {}) if self._active(documents[0]) else {},
                "child_snapshot": documents[1],
                "conversation_snapshot": documents[2] if conversation_id is not None else None}

    @staticmethod
    def _conversation_response(document) -> dict:
        data = document.to_dict()
        return {"id": document.id, "child_id": data["child_id"],
                "title": data["title"], "created_at": data["created_at"],
                "updated_at": data["updated_at"]}

    def create_conversation(self, uid: str, child_id: str, *, conversation_id: str | None = None) -> dict | None:
        document = self._conversations(uid).document(conversation_id) if conversation_id else self._conversations(uid).document()
        now = datetime.now(timezone.utc)
        values = {"child_id": child_id, "title": "New conversation", "created_at": now, "updated_at": now}
        @firestore.transactional
        def create(transaction):
            account, child = self._transaction_documents(
                transaction, [self._account(uid), self._children(uid).document(child_id)], ("deleting",),
            )
            if not self._active(account) or not self._active(child):
                return False
            # A create precondition prevents collisions from overwriting a chat.
            transaction.create(document, values)
            return True

        return {"id": document.id, **values} if create(self.client.transaction()) else None

    def list_conversations(self, uid: str, child_id: str, limit: int = 30,
                           before: str | None = None) -> list[dict]:
        query = self._conversations(uid).where(filter=FieldFilter("child_id", "==", child_id))
        query = query.order_by("updated_at", direction=firestore.Query.DESCENDING)
        if before is not None:
            cursor = self._conversations(uid).document(before).get()
            if not cursor.exists or cursor.to_dict().get("child_id") != child_id:
                raise ValueError("Invalid conversation cursor.")
            query = query.start_after(cursor)
        # Bound database reads instead of loading an account's entire history.
        query = query.limit(limit)
        return [self._conversation_response(document) for document in query.stream()]

    def get_conversation(self, uid: str, conversation_id: str, limit: int = 50,
                         before: str | None = None, *, expected_child_id: str | None = None,
                         prefetched_snapshot=None) -> dict | None:
        document = self._conversations(uid).document(conversation_id)
        snapshot = prefetched_snapshot if prefetched_snapshot is not None else document.get()
        if prefetched_snapshot is not None and snapshot.reference.path != document.path:
            raise ValueError("Invalid conversation snapshot.")
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data.get("deleting", False) or (expected_child_id is not None and data.get("child_id") != expected_child_id):
            return None
        messages_collection = document.collection("messages")
        query = messages_collection.order_by("sequence", direction=firestore.Query.DESCENDING)
        if before is not None:
            cursor = messages_collection.document(before).get()
            if not cursor.exists:
                raise ValueError("Invalid message cursor.")
            query = query.start_after(cursor)
        query = query.limit(limit)
        messages = [{**message.to_dict(), "id": message.id} for message in query.stream()]
        return {**self._conversation_response(snapshot), "messages": list(reversed(messages))}

    def save_conversation_turn(self, uid: str, conversation_id: str, child_id: str,
                               question: str, routine: str | None, response: dict) -> str:
        """Save both messages together, after rechecking ownership at write time."""
        conversation = self._conversations(uid).document(conversation_id)
        messages = conversation.collection("messages")
        question_document, answer_document = messages.document(), messages.document()

        @firestore.transactional
        def save(transaction):
            snapshot, child, account = self._transaction_documents(
                transaction, [conversation, self._children(uid).document(child_id), self._account(uid)],
                ("child_id", "message_count", "deleting"),
            )
            if (not self._active(account) or not snapshot.exists or not child.exists
                    or snapshot.to_dict().get("child_id") != child_id):
                raise ValueError("Conversation not found for the selected child.")
            data = snapshot.to_dict()
            if data.get("deleting", False) or child.to_dict().get("deleting", False):
                raise ValueError("Conversation not found for the selected child.")
            sequence = data.get("message_count", 0)
            common = {"created_at": firestore.SERVER_TIMESTAMP, "routine": routine}
            transaction.set(question_document, {**common, "role": "user", "text": question,
                                                "sequence": sequence})
            transaction.set(answer_document, {
                **common, **response, "role": "assistant", "sequence": sequence + 1,
            })
            update = {"message_count": sequence + 2, "updated_at": firestore.SERVER_TIMESTAMP}
            if sequence == 0:
                update["title"] = " ".join(question.split())[:80]
            transaction.update(conversation, update)

        save(self.client.transaction())
        return answer_document.id

    def save_message_feedback(self, uid: str, conversation_id: str, message_id: str,
                              helpful: bool | None, comment: str | None, *, rating: int | None = None,
                              reasons: list[str] | None = None) -> datetime | None:
        conversation = self._conversations(uid).document(conversation_id)
        message = conversation.collection("messages").document(message_id)
        feedback = self._feedback_data(helpful, comment, rating=rating, reasons=reasons)

        @firestore.transactional
        def save(transaction):
            parent, snapshot, account = self._transaction_documents(
                transaction, [conversation, message, self._account(uid)], ("role", "deleting"),
            )
            if (not self._active(account) or not parent.exists or not snapshot.exists
                    or snapshot.to_dict().get("role") != "assistant"):
                return None
            if parent.to_dict().get("deleting", False):
                return None
            transaction.update(message, {"feedback": feedback})
            return feedback["recorded_at"]

        return save(self.client.transaction())

    def delete_conversation(self, uid: str, conversation_id: str) -> bool:
        document = self._conversations(uid).document(conversation_id)
        if not document.get().exists:
            return False
        # Reject in-flight message writes while recursive cleanup is running.
        document.update({"deleting": True})
        self.client.recursive_delete(document)
        return True

    @staticmethod
    def _child_response(document) -> dict:
        data = document.to_dict() or {}
        dob = data["date_of_birth"]
        if isinstance(dob, datetime):
            dob = dob.date()
        if isinstance(dob, str):
            dob = date.fromisoformat(dob)
        today = current_date()
        # A profile can age out after creation. Keep it readable/deletable while
        # the coaching endpoint enforces eligibility independently of UI state.
        age_days, age_months, age_label = calculate_age(dob, today, enforce_scope=False)
        _, completed_months, _ = age_details(dob, today)
        in_scope = within_project_scope(dob, today)
        return {"id": document.id, "name": data["name"], "date_of_birth": dob,
                "age_months": age_months, "age_days": age_days,
                "completed_months": completed_months, "age_label": age_label,
                "in_scope": in_scope,
                "milestone_focus": data.get("milestone_focus"),
                "milestones": data.get("milestones", [data["milestone_focus"]] if data.get("milestone_focus") else []),
                "health_details": data.get("health_details") or {},
                "use_health_details": data.get("use_health_details") is True,
                "health_context_available": health_context_available(),
                "health_context_revision": data.get("health_context_revision"),
                "baseline_milestones": baseline_milestones(completed_months) if in_scope else [], "created_at": data.get("created_at")}

    def list_children(self, uid: str) -> list[dict]:
        return [self._child_response(document) for document in self._children(uid).stream()]

    def get_child(self, uid: str, child_id: str) -> dict | None:
        document = self._children(uid).document(child_id).get()
        return self._child_response(document) if self._active(document) else None

    def create_child(self, uid: str, name: str, date_of_birth: date, milestone_focus: str | None, milestones: list[str] | None = None,
                     *, health_details: dict | None = None, use_health_details: bool = False) -> dict:
        calculate_age(date_of_birth)
        notes = ChildHealthDetails.model_validate(health_details or {}).model_dump()
        if use_health_details and not health_context_available():
            raise ValueError("Using health details in replies is currently unavailable. You can save them privately.")
        document = self._children(uid).document()
        values = {"name": name.strip(), "date_of_birth": date_of_birth.isoformat(),
                      "milestone_focus": milestone_focus.strip() if milestone_focus else None,
                      "milestones": [value.strip() for value in (milestones or []) if value.strip()],
                      "health_details": notes, "use_health_details": use_health_details,
                      "health_context_revision": uuid4().hex,
                      "created_at": firestore.SERVER_TIMESTAMP}

        @firestore.transactional
        def create(transaction):
            account = self._account(uid).get(transaction=transaction)
            if not self._active(account):
                raise ValueError("Account data is unavailable. Review privacy consent before retrying.")
            transaction.create(document, values)

        create(self.client.transaction())
        return self.get_child(uid, document.id)

    def update_child(self, uid: str, child_id: str, changes: dict) -> dict | None:
        document = self._children(uid).document(child_id)
        update = {}
        if changes.get("name") is not None:
            update["name"] = changes["name"].strip()
        if changes.get("date_of_birth") is not None:
            calculate_age(changes["date_of_birth"])
            update["date_of_birth"] = changes["date_of_birth"].isoformat()
        if "milestone_focus" in changes:
            value = changes["milestone_focus"]
            update["milestone_focus"] = value.strip() if value else None
        if changes.get("milestones") is not None:
            update["milestones"] = [value.strip() for value in changes["milestones"] if value.strip()]
        if "health_details" in changes:
            update["health_details"] = ChildHealthDetails.model_validate(changes["health_details"] or {}).model_dump()
        if changes.get("use_health_details") is not None:
            if changes["use_health_details"] and not health_context_available():
                raise ValueError("Using health details in replies is currently unavailable. You can save them privately.")
            update["use_health_details"] = changes["use_health_details"]
        if "health_details" in update or "use_health_details" in update:
            # A new revision prevents old health-tailored replies from restoring removed notes.
            update["health_context_revision"] = uuid4().hex
        @firestore.transactional
        def save(transaction):
            child, account = self._transaction_documents(
                transaction, [document, self._account(uid)], ("deleting",),
            )
            if not self._active(account) or not self._active(child):
                return False
            if update:
                transaction.update(document, update)
            return True

        if not save(self.client.transaction()):
            return None
        return self.get_child(uid, child_id)

    def create_interaction(self, uid: str, child_id: str, question: str, routine: str | None, answer: str, citations: list[dict], status: str = "answered", *, vaccination_country: str | None = None, response_kind: str | None = None, answer_basis: str | None = None, reference_status: str | None = None) -> str:
        document = self._interactions(uid).document()
        values = {"child_id": child_id, "question": question, "routine": routine,
                      "answer": answer, "citations": citations, "status": status,
                      **({"vaccination_country": vaccination_country} if vaccination_country else {}),
                      **({"response_kind": response_kind} if response_kind else {}),
                      **({"answer_basis": answer_basis, "reference_status": reference_status} if answer_basis else {}),
                      "created_at": firestore.SERVER_TIMESTAMP}

        @firestore.transactional
        def save(transaction):
            account, child = self._transaction_documents(
                transaction, [self._account(uid), self._children(uid).document(child_id)], ("deleting",),
            )
            if not self._active(account) or not self._active(child):
                raise ValueError("Child profile not found.")
            transaction.create(document, values)

        save(self.client.transaction())
        return document.id

    def save_feedback(self, uid: str, interaction_id: str, helpful: bool | None, comment: str | None,
                      *, rating: int | None = None, reasons: list[str] | None = None) -> datetime | None:
        document = self._interactions(uid).document(interaction_id)
        feedback = self._feedback_data(helpful, comment, rating=rating, reasons=reasons)

        @firestore.transactional
        def save(transaction):
            snapshot, account = self._transaction_documents(
                transaction, [document, self._account(uid)], ("deleting",),
            )
            if not self._active(account) or not snapshot.exists:
                return None
            transaction.update(document, {"feedback": feedback})
            return feedback["recorded_at"]

        return save(self.client.transaction())

    @staticmethod
    def _feedback_data(helpful: bool | None, comment: str | None, *, rating: int | None = None,
                       reasons: list[str] | None = None) -> dict:
        from backend.schemas.coaching import FeedbackValues

        # Validate at the storage boundary too; do not infer numeric ratings from
        # historical boolean feedback. Shared-comment access is checked against
        # the current privacy notice when building the administrator report.
        value = FeedbackValues(helpful=helpful, rating=rating, reasons=reasons or [], comment=comment)
        return {**value.model_dump(), "comment": comment.strip() if comment else None,
                "recorded_at": datetime.now(timezone.utc)}

    def delete_child(self, uid: str, child_id: str) -> bool:
        # Query only this user's interactions; recursive deletion includes future subcollections.
        child = self._children(uid).document(child_id)
        if not child.get().exists:
            return False
        child.update({"deleting": True})
        interactions = self._interactions(uid).where(filter=FieldFilter("child_id", "==", child_id))
        for interaction in interactions.stream():
            self.client.recursive_delete(interaction.reference)
        conversations = self._conversations(uid).where(filter=FieldFilter("child_id", "==", child_id))
        for conversation in conversations.stream():
            self.client.recursive_delete(conversation.reference)
        self.client.recursive_delete(child)
        return True

    def delete_account_data(self, uid: str) -> None:
        account = self._account(uid)
        # Keep the barrier until every descendant deletion has completed. Passing
        # the parent to BulkWriter recursive_delete can schedule its delete while
        # descendant deletes are still in flight. Failure leaves a retryable marker.
        account.set({"deleting": True}, merge=True)
        for collection in account.collections():
            self.client.recursive_delete(collection)
        account.delete()
