"""Reset lost authenticators from a trusted administrator workstation; preview by default."""

import argparse
import re

from backend.core.firebase import initialize_firebase
from backend.services.account_security import AccountSecurityService


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--identity-verified", action="store_true",
                        help="Confirm that the account owner's identity was independently verified.")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[^/\s]{1,128}", args.uid):
        parser.error("Provide a valid account UID.")
    if not args.apply:
        print("Preview: reset authenticators and revoke existing sessions. No account changed.")
        return
    if not args.identity_verified:
        parser.error("Independently verify the account owner's identity before recovery.")
    AccountSecurityService(initialize_firebase()).disable_mfa(args.uid, recovery=True)
    print("Authenticators reset and sessions revoked. Mandatory MFA policy remains in force.")


if __name__ == "__main__":
    main()
