// this custom hook gives components an easy way to read auth state from AuthProvider.
// it is imported in App.jsx to check whether someone is currently signed in.
import { useContext } from "react";
import { AuthContext } from "../context/AuthContext";

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
