import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyBYctxD03Vlb2A71t4KclW1tGhyIWtdrrE",
  authDomain: "voice-interaction-system.firebaseapp.com",
  projectId: "voice-interaction-system",
  appId: "1:489399450516:web:7d2c793ba3f6207be96d81",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
