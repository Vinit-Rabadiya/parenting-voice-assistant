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

const provider = new GoogleAuthProvider();

export const signInWithGoogle = async () => {
  try {
    const result = await signInWithPopup(auth, provider);
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

export const signInWithEmail = async (email, password) => {
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
  const result = await createUserWithEmailAndPassword(auth, email, password);
  let verificationEmailRequested;
  try {
    await sendEmailVerification(result.user);
    verificationEmailRequested = true;
  } catch {
    verificationEmailRequested = false;
  }
  return { user: result.user, verificationEmailRequested };
};

export const checkEmailVerification = async () => {
  const user = auth.currentUser;
  if (user === null) {
    throw new Error("Sign in before checking email verification.");
  }
  await reload(user);
  return user.emailVerified;
};

export const resendVerificationEmail = async () => {
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
  await signOut(auth);
};

export const requestPasswordReset = async (email) => {
  await sendPasswordResetEmail(auth, email);
};

export const beginTotpEnrollment = async () => {
  const user = auth.currentUser;
  if (user === null) {
    throw new Error("Login is required.");
  }

  await reload(user);
  if (user.emailVerified === false) {
    throw new Error("Email verification is required.");
  }

  if (
    multiFactor(user).enrolledFactors.some(
      (factor) => factor.factorId === TotpMultiFactorGenerator.FACTOR_ID,
    )
  ) {
    throw new Error("An authenticator is already enrolled.");
  }

  const session = await multiFactor(user).getSession();
  const secret = await TotpMultiFactorGenerator.generateSecret(session);

  return { userId: user.uid, secret };
};

export const completeTotpSignIn = async (resolver, code) => {
  if (!resolver) {
    throw new Error("Login challenge is missing. Please log in again.");
  }

  const otp = code.trim();

  if (!/^[0-9]{6}$/.test(otp)) {
    throw new Error("Enter the six-digit authenticator code.");
  }

  const factor = resolver.hints.find(
    (hint) => hint.factorId === TotpMultiFactorGenerator.FACTOR_ID,
  );

  if (!factor) {
    throw new Error("No supported authenticator was found for this login.");
  }

  const assertion = TotpMultiFactorGenerator.assertionForSignIn(
    factor.uid,
    otp,
  );

  const result = await resolver.resolveSignIn(assertion);
  return result.user;
};

export const confirmTotpEnrollment = async (pending, code) => {
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

  await multiFactor(user).enroll(assertion, "Authenticator");
};
