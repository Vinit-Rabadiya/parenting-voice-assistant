"""Grant or revoke aggregate-only access from a trusted server; preview by default."""
import argparse
import re

from firebase_admin import auth

from backend.core.firebase import initialize_firebase

CLAIM = "feedback_summary_admin"


def update_permission(uid, *, grant, app):
    account = auth.get_user(uid, app=app)
    if grant and (account.disabled or not account.email_verified):
        raise ValueError("Grant requires an enabled account with verified email.")
    claims = dict(account.custom_claims or {})
    if grant:
        claims[CLAIM] = True
    else:
        claims.pop(CLAIM, None)
    auth.set_custom_user_claims(uid, claims, app=app)
    # The backend already verifies tokens with check_revoked=True.
    auth.revoke_refresh_tokens(uid, app=app)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--grant", action="store_true")
    action.add_argument("--revoke", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[^/\s]{1,128}", args.uid):
        parser.error("Provide a valid account UID.")
    if not args.apply:
        print(f"Preview: {'grant' if args.grant else 'revoke'} aggregate feedback permission. No account changed. Add --apply to proceed.")
        return
    app = initialize_firebase()
    update_permission(args.uid, grant=args.grant, app=app)
    print("Aggregate feedback permission updated; existing sessions revoked. Sign in again.")


if __name__ == "__main__":
    main()
