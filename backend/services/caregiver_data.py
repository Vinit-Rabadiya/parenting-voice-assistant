"""Firestore access scoped to one authenticated caregiver at a time."""

from datetime import date, datetime, timezone

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from backend.services.age import age_details, current_date


MAX_PROJECT_AGE_DAYS = 24 * 31

BASELINE_MILESTONES = (
    (2, ["Social smile and follows a colourful object"]),
    (4, ["Holds the head upright", "Responds to sound and familiar voices"]),
    (6, ["Rolls over", "Reaches for and grasps objects", "Babbles"]),
    (9, ["Sits without support", "Transfers objects between hands"]),
    (12, ["Takes steps with support", "Uses simple gestures", "Says 2 to 3 words"]),
    (18, ["Walks without support", "Drinks from a cup", "Points to body parts on request"]),
    (25, ["Kicks a ball", "Builds a tower with blocks", "Uses short sentences"]),
)


def calculate_age(date_of_birth: date, today: date | None = None) -> tuple[int, float, str]:
    """Calculate the display age on the server; clients never supply it as authority."""
    age_days, completed_months, calendar_months = age_details(date_of_birth, today)
    if age_days > MAX_PROJECT_AGE_DAYS:
        raise ValueError("This prototype supports children from birth through 24 months.")
    age_months = round(calendar_months, 1)
    if completed_months == 0:
        age_label = f"{age_days} day{'s' if age_days != 1 else ''}"
    elif age_months < 24:
        age_label = f"{age_months:g} months"
    else:
        age_label = "24 months"
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

    def _interactions(self, uid: str):
        return self.client.collection("users").document(uid).collection("interactions")

    @staticmethod
    def _child_response(document) -> dict:
        data = document.to_dict() or {}
        dob = data["date_of_birth"]
        if isinstance(dob, datetime):
            dob = dob.date()
        if isinstance(dob, str):
            dob = date.fromisoformat(dob)
        today = current_date()
        age_days, age_months, age_label = calculate_age(dob, today)
        _, completed_months, _ = age_details(dob, today)
        return {"id": document.id, "name": data["name"], "date_of_birth": dob,
                "age_months": age_months, "age_days": age_days,
                "completed_months": completed_months, "age_label": age_label,
                "milestone_focus": data.get("milestone_focus"),
                "milestones": data.get("milestones", [data["milestone_focus"]] if data.get("milestone_focus") else []),
                "baseline_milestones": baseline_milestones(completed_months), "created_at": data.get("created_at")}

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

    def create_interaction(self, uid: str, child_id: str, question: str, routine: str | None, answer: str, citations: list[dict], status: str = "answered") -> str:
        document = self._interactions(uid).document()
        document.set({"child_id": child_id, "question": question, "routine": routine,
                      "answer": answer, "citations": citations, "status": status, "created_at": firestore.SERVER_TIMESTAMP})
        return document.id

    def save_feedback(self, uid: str, interaction_id: str, helpful: bool, comment: str | None) -> datetime | None:
        document = self._interactions(uid).document(interaction_id)
        if not document.get().exists:
            return None
        recorded_at = datetime.now(timezone.utc)
        document.update({"feedback": {"helpful": helpful, "comment": comment.strip() if comment else None, "recorded_at": recorded_at}})
        return recorded_at

    def delete_child(self, uid: str, child_id: str) -> bool:
        # Query only this user's interactions; recursive deletion includes future subcollections.
        child = self._children(uid).document(child_id)
        if not child.get().exists:
            return False
        interactions = self._interactions(uid).where(filter=FieldFilter("child_id", "==", child_id))
        for interaction in interactions.stream():
            self.client.recursive_delete(interaction.reference)
        self.client.recursive_delete(child)
        return True

    def delete_account_data(self, uid: str) -> None:
        # Deleting just the parent document would leave Firestore subcollections behind.
        self.client.recursive_delete(self.client.collection("users").document(uid))
