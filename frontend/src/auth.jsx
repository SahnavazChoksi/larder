import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api, { getTokens, setTokens } from "./api";
import { isOfflineError } from "./offline";

const AuthContext = createContext(null);
const RANK = { cook: 0, server: 0, manager: 1, owner: 2 };
const LOCATION_KEY = "larder.location";
const ME_KEY = "larder.me"; // last known profile, so a signed-in tablet still opens when the server is down

function cachedMe() {
  try {
    return JSON.parse(localStorage.getItem(ME_KEY));
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getTokens()));
  const [locationId, setLocationIdState] = useState(() => Number(localStorage.getItem(LOCATION_KEY)) || null);

  const loadMe = useCallback(async () => {
    const { data } = await api.get("/auth/me/");
    setUser(data);
    localStorage.setItem(ME_KEY, JSON.stringify(data));
    return data;
  }, []);

  useEffect(() => {
    if (!getTokens()) return;
    loadMe()
      .catch((err) => {
        const me = cachedMe();
        if (isOfflineError(err) && me) setUser(me);
        else setTokens(null);
      })
      .finally(() => setLoading(false));
  }, [loadMe]);

  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener("larder:logout", onLogout);
    return () => window.removeEventListener("larder:logout", onLogout);
  }, []);

  const login = useCallback(
    async (username, password) => {
      const { data } = await api.post("/auth/token/", { username, password });
      setTokens(data);
      return loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(() => {
    setTokens(null);
    localStorage.removeItem(ME_KEY);
    setUser(null);
  }, []);

  const setLocationId = useCallback((id) => {
    setLocationIdState(id);
    localStorage.setItem(LOCATION_KEY, String(id));
  }, []);

  const value = useMemo(() => {
    const locations = user?.locations || [];
    const location = locations.find((l) => l.id === locationId) || locations.find((l) => l.kind === "outlet") || locations[0] || null;
    return {
      user,
      loading,
      login,
      logout,
      locations,
      location,
      setLocationId,
      can: (role) => Boolean(user) && RANK[user.role] >= RANK[role],
    };
  }, [user, loading, login, logout, locationId, setLocationId]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
