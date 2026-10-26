import { beforeEach, expect, it, vi } from "vitest";
import { signInWithGoogle, completeTotpSignIn, getAccountSecurityStatus, reauthenticateAccount, turnOffMfa,
  beginTotpEnrollment, confirmTotpEnrollment } from "../../frontend/src/services/auth";
import { auth } from "../../frontend/src/services/firebase";
import { getAccountSecurity, disableAccountMfa } from "../../frontend/src/services/caregiving";
import { signInWithPopup, multiFactor, TotpMultiFactorGenerator, reauthenticateWithPopup } from "firebase/auth";

vi.mock("../../frontend/src/services/firebase", () => ({ auth: { currentUser: null } }));
vi.mock("../../frontend/src/services/caregiving", () => ({ getAccountSecurity: vi.fn(), disableAccountMfa: vi.fn() }));
vi.mock("firebase/auth", async (original) => ({ ...(await original()),
  signInWithPopup: vi.fn(), reload: vi.fn(), multiFactor: vi.fn(), reauthenticateWithPopup: vi.fn(),
  TotpMultiFactorGenerator: { FACTOR_ID: "totp", assertionForSignIn: vi.fn(), generateSecret: vi.fn(), assertionForEnrollment: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
  auth.currentUser = { uid: "one", emailVerified: true, email: "one@example.test",
    getIdToken: vi.fn().mockResolvedValue("token"),
    getIdTokenResult: vi.fn().mockResolvedValue({ claims: { firebase: { sign_in_provider: "google.com" } } }) };
  multiFactor.mockReturnValue({ enrolledFactors: [] });
  getAccountSecurity.mockResolvedValue({ mfa_required: false, mfa_enabled: false });
  TotpMultiFactorGenerator.assertionForEnrollment.mockReturnValue({ factorId: "totp" });
});

it("allows Google sign-in without requiring authenticator enrollment", async () => {
  signInWithPopup.mockResolvedValue({ user: auth.currentUser });
  expect((await signInWithGoogle()).next).toBe("signed-in");
  const status = await getAccountSecurityStatus();
  expect(status).toMatchObject({ emailVerified: true, totpEnrolled: false, mfaRequired: false });
});

it("never marks an unverified Google email as verified locally", async () => {
  auth.currentUser.emailVerified = false;
  expect((await getAccountSecurityStatus()).emailVerified).toBe(false);
  expect(getAccountSecurity).not.toHaveBeenCalled();
});

it("uses the selected backup authenticator to finish sign-in", async () => {
  const resolver = { hints: [{ uid: "main", factorId: "totp" }, { uid: "backup", factorId: "totp" }],
    resolveSignIn: vi.fn().mockResolvedValue({ user: auth.currentUser }) };
  await completeTotpSignIn(resolver, "012345", "backup");
  expect(TotpMultiFactorGenerator.assertionForSignIn).toHaveBeenCalledWith("backup", "012345");
  await expect(completeTotpSignIn(resolver, "012345", "unknown")).rejects.toThrow("No supported authenticator");
});

it("reauthenticates Google users before security changes and rejects account changes", async () => {
  const user = auth.currentUser;
  expect((await reauthenticateAccount("", "one")).next).toBe("signed-in");
  expect(reauthenticateWithPopup).toHaveBeenCalledWith(user, expect.anything());
  await expect(turnOffMfa("another-account")).rejects.toThrow("Account changed");
  expect(disableAccountMfa).not.toHaveBeenCalled();
});

it("enrolls a separately verified backup authenticator without replacing the first", async () => {
  const enroll = vi.fn();
  multiFactor.mockReturnValue({ enrolledFactors: [{ uid: "main", factorId: "totp" }],
    getSession: vi.fn().mockResolvedValue("enrollment-session"), enroll });
  const secret = { secretKey: "test-only-key" };
  TotpMultiFactorGenerator.generateSecret.mockResolvedValue(secret);
  const pending = await beginTotpEnrollment();
  expect(pending.displayName).toBe("Backup authenticator");
  await confirmTotpEnrollment(pending, "012345");
  expect(TotpMultiFactorGenerator.assertionForEnrollment).toHaveBeenCalledWith(secret, "012345");
  expect(enroll).toHaveBeenCalledWith(expect.anything(), "Backup authenticator");
});

it("does not return an enrollment secret after the account changes", async () => {
  multiFactor.mockReturnValue({ enrolledFactors: [], getSession: vi.fn().mockResolvedValue("session") });
  TotpMultiFactorGenerator.generateSecret.mockImplementationOnce(async () => {
    auth.currentUser = { uid: "different-account" };
    return { secretKey: "test-only-secret" };
  });
  await expect(beginTotpEnrollment()).rejects.toMatchObject({ code: "app/account-changed" });
});

it("returns a specific error when two authenticators are already enrolled", async () => {
  multiFactor.mockReturnValue({ enrolledFactors: [{ factorId: "totp" }, { factorId: "totp" }] });
  await expect(beginTotpEnrollment()).rejects.toMatchObject({ code: "app/authenticator-limit" });
});

it("does not treat an unreadable mandatory-MFA policy as optional", async () => {
  getAccountSecurity.mockResolvedValue({});
  await expect(getAccountSecurityStatus()).rejects.toThrow("Account security could not be confirmed");
});
