import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

// these project settings are visible in the browser; never put private keys here.
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

// prepare firebase once and share its login connection with the other browser files.
const app = initializeApp(firebaseConfig);
// use firebase's default browser setting for remembering login across reloads.
export const auth = getAuth(app);
