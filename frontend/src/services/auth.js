import {
  GoogleAuthProvider,
  signInWithPopup,
  createUserWithEmailAndPassword,
  sendEmailVerification,
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
  } catch  {
    verificationEmailRequested = false;
  }
  return { user: result.user, verificationEmailRequested };
};
