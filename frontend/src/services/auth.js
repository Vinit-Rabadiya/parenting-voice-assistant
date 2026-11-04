// this file contains all browser firebase auth actions (login, signup, mfa, reset, logout).
// it is imported by components (LoginForm, SignUpForm, GoogleSignInButton) and pages (AccountPage).
import {
  GoogleAuthProvider,
  signInWithPopup,
  createUserWithEmailAndPassword,
  sendEmailVerification,
  reload,
  signInWithEmailAndPassword,
  signOut,
  sendPasswordResetEmail,
  multiFactor,
  TotpMultiFactorGenerator,
  getMultiFactorResolver,
  reauthenticateWithPopup,
  reauthenticateWithCredential,
  EmailAuthProvider,
} from "firebase/auth";
import { auth } from "./firebase";
import { getAccountSecurity, disableAccountMfa } from "./caregiving";

// keep firebase calls here and let the pages choose screens and messages.
const provider = new GoogleAuthProvider();
// Display summaries only. API authorization and security mutations always check the server.
const securitySummaries = new WeakMap();
const SECURITY_SUMMARY_MS = 60000;

function enrollmentError(code, message) {
  return Object.assign(new Error(message), { code });
}

export const signInWithGoogle = async () => {
  // google login may still need an authenticator code before login is complete.
  try {
    const result = await signInWithPopup(auth, provider);
    return { next: "signed-in", user: result.user };
  } catch (error) {
    if (error.code === "auth/multi-factor-auth-required") {
      return {
        next: "mfa-required",
        // give the page what it needs to finish this login with an authenticator code.
        resolver: getMultiFactorResolver(auth, error),
      };
    }
    throw error;
  }
};

export const signInWithEmail = async (email, password) => {
  // return the same kinds of answers as google login so both use one code-entry form.
  try {
    const result = await signInWithEmailAndPassword(auth, email, password);
    return { next: "signed-in", user: result.user };
  } catch (error) {
    if (error.code === "auth/multi-factor-auth-required") {
      return {
        next: "mfa-required",
        resolver: getMultiFactorResolver(auth, error),
      };
    }
    throw error;
  }
};

export const signUpWithEmail = async (email, password) => {
  // creating the account also logs it in, even if requesting the email later fails.
  const result = await createUserWithEmailAndPassword(auth, email, password);
  let verificationEmailRequested;
  try {
    await sendEmailVerification(result.user);
    verificationEmailRequested = true;
  } catch {
    verificationEmailRequested = false;
  }
  // a successful email request does not mean the user received or clicked the link.
  return { user: result.user, verificationEmailRequested };
};

export const resendVerificationEmail = async () => {
  // send another email for this account instead of creating another account.
  const user = auth.currentUser;
  if (user === null) {
    throw new Error("Sign-in is required");
  }
  await reload(user);
  if (user.emailVerified) return { status: "already-verified" };
  await sendEmailVerification(user);
  return { status: "email-requested" };
};

export const logOut = async () => {
  // log out this browser; other devices and previously copied login tokens may still work.
  if (auth.currentUser) securitySummaries.delete(auth.currentUser);
  await signOut(auth);
};

export const requestPasswordReset = async (email) => {
  // request a reset while logged out; changing the password does not remove the authenticator.
  await sendPasswordResetEmail(auth, email);
};

export const beginTotpEnrollment = async () => {
  // require a signed-in user with a verified email before starting authenticator setup.
  const user = auth.currentUser;
  if (user === null) {
    throw enrollmentError("app/login-required", "Login is required.");
  }

  await reload(user);
  if (user.emailVerified !== true) {
    throw enrollmentError("auth/unverified-email", "Email verification is required.");
  }

  const count = multiFactor(user).enrolledFactors.length;
  if (count >= 2) {
    throw enrollmentError("app/authenticator-limit", "Two authenticators are already enrolled.");
  }
  if (auth.currentUser !== user) throw enrollmentError("app/account-changed", "Account changed. Please try again.");

  // get temporary permission from firebase to start this user's authenticator setup.
  await user.getIdToken(true);
  if (auth.currentUser !== user) throw enrollmentError("app/account-changed", "Account changed. Please try again.");
  const session = await multiFactor(user).getSession();
  const secret = await TotpMultiFactorGenerator.generateSecret(session);
  if (auth.currentUser !== user) throw enrollmentError("app/account-changed", "Account changed. Please try again.");

  // return the secret for setup; the user must still confirm a code to finish adding it.
  return { userId: user.uid, secret, displayName: count ? "Backup authenticator" : "Authenticator" };
};

export const completeTotpSignIn = async (resolver, code, factorUid = null) => {
  // use the entered code to finish the login that firebase is waiting to complete.
  if (!resolver) {
    throw new Error("Login challenge is missing. Please log in again.");
  }

  // keep the code as text so a starting zero is not lost.
  const otp = code.trim();

  if (!/^[0-9]{6}$/.test(otp)) {
    throw new Error("Enter the six-digit authenticator code.");
  }

  // find the first time-based authenticator listed for this login attempt.
  const factor = resolver.hints.find(
    (hint) => hint.factorId === TotpMultiFactorGenerator.FACTOR_ID && (!factorUid || hint.uid === factorUid),
  );

  if (!factor) {
    throw new Error("No supported authenticator was found for this login.");
  }

  // prepare the authenticator details and code for firebase to check.
  const assertion = TotpMultiFactorGenerator.assertionForSignIn(
    factor.uid,
    otp,
  );

  // completing login tells the app that a user is now signed in.
  const result = await resolver.resolveSignIn(assertion);
  return result.user;
};

export const confirmTotpEnrollment = async (pending, code) => {
  // make sure the account finishing setup is the one that started it.
  const user = auth.currentUser;

  if (!user || !pending || user.uid !== pending.userId) {
    throw enrollmentError("app/account-changed", "The account changed. Start authenticator setup again.");
  }
  await reload(user);

  if (!user.emailVerified) {
    throw enrollmentError("auth/unverified-email", "Verify your email before setting up an authenticator.");
  }
  const otp = code.trim();

  if (!/^[0-9]{6}$/.test(otp)) {
    throw new Error("Enter the six-digit authenticator code.");
  }

  const assertion = TotpMultiFactorGenerator.assertionForEnrollment(
    pending.secret,
    otp,
  );

  // firebase checks the code and adds the authenticator; scanning alone does not finish setup.
  if (auth.currentUser !== user) throw new Error("Account changed. Start authenticator setup again.");
  await multiFactor(user).enroll(assertion, pending.displayName || "Authenticator");
  securitySummaries.delete(user);
};

export const getAccountSecurityStatus = async ({ refresh = false } = {}) => {
  // fetch saved account details so the page stays correct after a reload.
  const user = auth.currentUser;

  if (!user) {
    throw new Error("Log in to check your account.");
  }

  const cached = securitySummaries.get(user);
  if (!refresh && cached && cached.expires > Date.now()) {
    const summary = await cached.promise;
    if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
    return summary;
  }
  const pending = { expires: Date.now() + SECURITY_SUMMARY_MS };
  const load = async () => {
    // Refreshing email verification explicitly needs Firebase reload; merely opening
    // settings uses the existing token and a live server policy read.
    if (refresh) await reload(user);
    if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
    if (refresh) await user.getIdToken(true);
    const policy = user.emailVerified ? await getAccountSecurity() : null;
    if (policy && (typeof policy.mfa_required !== "boolean" || typeof policy.mfa_enabled !== "boolean")) {
      throw new Error("Account security could not be confirmed. Please try again.");
    }
    if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
    const token = await user.getIdTokenResult();
    if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");

    return {
      emailVerified: user.emailVerified,
      mfaRequired: policy?.mfa_required ?? false,
      factorCount: multiFactor(user).enrolledFactors.length,
      usesGoogle: token.claims.firebase?.sign_in_provider === "google.com",
      // An enrolled authenticator does not prove its code was used for this login.
      totpEnrolled: policy?.mfa_enabled ?? multiFactor(user).enrolledFactors.some(
        (factor) => factor.factorId === TotpMultiFactorGenerator.FACTOR_ID,
      ),
    };
  };
  pending.promise = load().catch((cause) => {
    if (securitySummaries.get(user) === pending) securitySummaries.delete(user);
    throw cause;
  });
  securitySummaries.set(user, pending);
  return pending.promise;
};

export const totpSignInFactors = (resolver) => resolver.hints.filter(
  (factor) => factor.factorId === TotpMultiFactorGenerator.FACTOR_ID,
);

export const reauthenticateAccount = async (password = "", expectedUid = auth.currentUser?.uid) => {
  const user = auth.currentUser;
  if (!user || user.uid !== expectedUid) throw new Error("Account changed. Please sign in again.");
  const token = await user.getIdTokenResult();
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  try {
    if (token.claims.firebase?.sign_in_provider === "google.com") {
      await reauthenticateWithPopup(user, provider);
    } else {
      if (!password) throw new Error("Enter your current password.");
      await reauthenticateWithCredential(user, EmailAuthProvider.credential(user.email, password));
    }
    if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
    return { next: "signed-in" };
  } catch (error) {
    if (error.code === "auth/multi-factor-auth-required") {
      return { next: "mfa-required", resolver: getMultiFactorResolver(auth, error) };
    }
    throw error;
  }
};

export const turnOffMfa = async (expectedUid = auth.currentUser?.uid) => {
  const user = auth.currentUser;
  if (!user || user.uid !== expectedUid) throw new Error("Account changed. Please sign in again.");
  await user.getIdToken(true);
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  await disableAccountMfa();
  securitySummaries.delete(user);
};
