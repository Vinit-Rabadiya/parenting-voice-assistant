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
} from "firebase/auth";
import { auth } from "./firebase";

// keep firebase calls here and let the pages choose screens and messages.
const provider = new GoogleAuthProvider();

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
    throw new Error("Login is required.");
  }

  await reload(user);
  if (user.emailVerified === false) {
    throw new Error("Email verification is required.");
  }

  // stop if this account already has a time-based authenticator.
  if (
    multiFactor(user).enrolledFactors.some(
      (factor) => factor.factorId === TotpMultiFactorGenerator.FACTOR_ID,
    )
  ) {
    throw new Error("An authenticator is already enrolled.");
  }

  // get temporary permission from firebase to start this user's authenticator setup.
  const session = await multiFactor(user).getSession();
  const secret = await TotpMultiFactorGenerator.generateSecret(session);

  // return the secret for setup; the user must still confirm a code to finish adding it.
  return { userId: user.uid, secret };
};

export const completeTotpSignIn = async (resolver, code) => {
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
    (hint) => hint.factorId === TotpMultiFactorGenerator.FACTOR_ID,
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
    throw new Error("The account changed. Start authenticator setup again.");
  }
  await reload(user);

  if (!user.emailVerified) {
    throw new Error("Verify your email before setting up an authenticator.");
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
  await multiFactor(user).enroll(assertion, "Authenticator");
};

export const getAccountSecurityStatus = async () => {
  // fetch saved account details so the page stays correct after a reload.
  const user = auth.currentUser;

  if (!user) {
    throw new Error("Log in to check your account.");
  }

  await reload(user);

  return {
    emailVerified: user.emailVerified,
    // an authenticator being set up does not prove its code was used for this login.
    totpEnrolled: multiFactor(user).enrolledFactors.some(
      (factor) => factor.factorId === TotpMultiFactorGenerator.FACTOR_ID,
    ),
  };
};
