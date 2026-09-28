// this file creates the react context object for storing shared auth state.
// it is imported in context/AuthProvider.jsx to supply state and in hooks/useAuth.js to read it.
import { createContext } from "react";

export const AuthContext = createContext(null);
