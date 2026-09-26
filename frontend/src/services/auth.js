import {
  GoogleAuthProvider,
  signInWithPopup,
  createUserWithEmailAndPassword,
  sendEmailVerification,
  reload,
} from "firebase/auth";
import { auth } from "./firebase";
const provider = new GoogleAuthProvider();

export const signInWithGoogle = async () => {
  const result = await signInWithPopup(auth, provider);
  return result.user;
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

export async function resendVerificationEmail() {
  const user = auth.currentUser;
  if (user === null) {
    throw new Error("Sign-in is required");
  }
  await reload(user);
  if (user.emailVerified) return { status: "already-verified" };
  await sendEmailVerification(user);
  return { status: "email-requested" };
}
