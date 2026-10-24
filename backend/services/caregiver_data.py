"""Firestore access scoped to one authenticated caregiver at a time."""

from datetime import date, datetime, timezone

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from backend.services.age import age_details, current_date, within_project_scope

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

    def _children(self, uid: str):
        return self.client.collection("users").document(uid).collection("children")

    def get_consent(self, uid: str) -> dict:
        document = self.client.collection("users").document(uid).get()
        return (document.to_dict() or {}) if document.exists else {}

    def save_consent(self, uid: str, version: str) -> datetime:
        document = self.client.collection("users").document(uid)

        @firestore.transactional
        def accept(transaction):
            snapshot = document.get(transaction=transaction)
            data = (snapshot.to_dict() or {}) if snapshot.exists else {}
            if (data.get("consent_version") == version and data.get("consent_at") is not None
                    and data.get("caregiver_authority") is True):
                return data["consent_at"]
            accepted_at = datetime.now(timezone.utc)
            transaction.set(document, {"consent_version": version, "consent_at": accepted_at,
                                       "caregiver_authority": True}, merge=True)
            return accepted_at

        return accept(self.client.transaction())

    def _interactions(self, uid: str):
        return self.client.collection("users").document(uid).collection("interactions")

    def _conversations(self, uid: str):
        return self.client.collection("users").document(uid).collection("conversations")

    @staticmethod
    def _conversation_response(document) -> dict:
        data = document.to_dict()
        return {"id": document.id, "child_id": data["child_id"],
                "title": data["title"], "created_at": data["created_at"],
                "updated_at": data["updated_at"]}

    def create_conversation(self, uid: str, child_id: str) -> dict | None:
        if self.get_child(uid, child_id) is None:
            return None
        document = self._conversations(uid).document()
        document.set({"child_id": child_id, "title": "New conversation",
                      "created_at": firestore.SERVER_TIMESTAMP,
                      "updated_at": firestore.SERVER_TIMESTAMP})
        return self._conversation_response(document.get())

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
                         before: str | None = None, *, expected_child_id: str | None = None) -> dict | None:
        document = self._conversations(uid).document(conversation_id)
        snapshot = document.get()
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
            snapshot = conversation.get(transaction=transaction)
            child = self._children(uid).document(child_id).get(transaction=transaction)
            if not snapshot.exists or not child.exists or snapshot.to_dict().get("child_id") != child_id:
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
            parent = conversation.get(transaction=transaction)
            snapshot = message.get(transaction=transaction)
            if not parent.exists or not snapshot.exists or snapshot.to_dict().get("role") != "assistant":
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
                "baseline_milestones": baseline_milestones(completed_months) if in_scope else [], "created_at": data.get("created_at")}

    def list_children(self, uid: str) -> list[dict]:
        return [self._child_response(document) for document in self._children(uid).stream()]

    def get_child(self, uid: str, child_id: str) -> dict | None:
        document = self._children(uid).document(child_id).get()
        return self._child_response(document) if document.exists else None

    def create_child(self, uid: str, name: str, date_of_birth: date, milestone_focus: str | None, milestones: list[str] | None = None) -> dict:
        calculate_age(date_of_birth)
        document = self._children(uid).document()
        document.set({"name": name.strip(), "date_of_birth": date_of_birth.isoformat(),
                      "milestone_focus": milestone_focus.strip() if milestone_focus else None,
                      "milestones": [value.strip() for value in (milestones or []) if value.strip()],
                      "created_at": firestore.SERVER_TIMESTAMP})
        return self.get_child(uid, document.id)

    def update_child(self, uid: str, child_id: str, changes: dict) -> dict | None:
        document = self._children(uid).document(child_id)
        if not document.get().exists:
            return None
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
        if update:
            document.update(update)
        return self.get_child(uid, child_id)

    def create_interaction(self, uid: str, child_id: str, question: str, routine: str | None, answer: str, citations: list[dict], status: str = "answered", *, vaccination_country: str | None = None, response_kind: str | None = None) -> str:
        document = self._interactions(uid).document()
        document.set({"child_id": child_id, "question": question, "routine": routine,
                      "answer": answer, "citations": citations, "status": status,
                      **({"vaccination_country": vaccination_country} if vaccination_country else {}),
                      **({"response_kind": response_kind} if response_kind else {}),
                      "created_at": firestore.SERVER_TIMESTAMP})
        return document.id

    def save_feedback(self, uid: str, interaction_id: str, helpful: bool | None, comment: str | None,
                      *, rating: int | None = None, reasons: list[str] | None = None) -> datetime | None:
        document = self._interactions(uid).document(interaction_id)
        if not document.get().exists:
            return None
        feedback = self._feedback_data(helpful, comment, rating=rating, reasons=reasons)
        document.update({"feedback": feedback})
        return feedback["recorded_at"]

    @staticmethod
    def _feedback_data(helpful: bool | None, comment: str | None, *, rating: int | None = None,
                       reasons: list[str] | None = None) -> dict:
        from backend.schemas.coaching import FeedbackValues

        # Validate at the storage boundary too; do not infer numeric ratings from
        # historical boolean feedback. There is no administrator review of
        # individual private feedback records.
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
        # Deleting just the parent document would leave Firestore subcollections behind.
        self.client.recursive_delete(self.client.collection("users").document(uid))
