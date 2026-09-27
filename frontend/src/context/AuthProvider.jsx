import { useState, useEffect } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "../services/firebase";
import { logOut } from "../services/auth";
import { AuthContext } from "./AuthContext";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [signupResult, setSignupResult] = useState(null);

  useEffect(() => {
    // listen to firebase to know when someone logs in or out.
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setCheckingAuth(false);
    });

    return unsubscribe;
  }, []);

  const handleLogout = async () => {
    await logOut();
    setUser(null);
    setSignupResult(null);
  };

  const value = {
    user,
    checkingAuth,
    signupResult,
    setSignupResult,
    logout: handleLogout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
