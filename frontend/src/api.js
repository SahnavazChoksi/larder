import axios from "axios";

const TOKENS_KEY = "larder.tokens";

export function getTokens() {
  try {
    return JSON.parse(localStorage.getItem(TOKENS_KEY)) || null;
  } catch {
    return null;
  }
}

export function setTokens(tokens) {
  if (tokens) localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
  else localStorage.removeItem(TOKENS_KEY);
}

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const tokens = getTokens();
  if (tokens?.access) config.headers.Authorization = `Bearer ${tokens.access}`;
  return config;
});

// When the access token expires, swap the refresh token for a new one once, then retry.
let refreshing = null;
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const tokens = getTokens();
    const isAuthCall = original?.url?.includes("/auth/token");
    if (error.response?.status === 401 && tokens?.refresh && !original._retry && !isAuthCall) {
      original._retry = true;
      try {
        refreshing = refreshing || axios.post("/api/auth/token/refresh/", { refresh: tokens.refresh });
        const { data } = await refreshing;
        refreshing = null;
        setTokens({ ...tokens, access: data.access });
        original.headers.Authorization = `Bearer ${data.access}`;
        return api(original);
      } catch {
        refreshing = null;
        setTokens(null);
        window.dispatchEvent(new Event("larder:logout"));
      }
    }
    return Promise.reject(error);
  },
);

function flatten(value) {
  if (Array.isArray(value)) return value.map(flatten).join(" ");
  if (value && typeof value === "object") return Object.values(value).map(flatten).join(" ");
  return String(value);
}

/** Turn a DRF error response into one readable sentence. */
export function errorText(err) {
  if (!err?.response) return "Can't reach the server. Is Django running on port 8000?";
  const data = err.response.data;
  if (!data || typeof data === "string") return `The server returned an error (${err.response.status}).`;
  if (data.detail) return flatten(data.detail);
  return Object.entries(data)
    .map(([field, msg]) => (field === "non_field_errors" ? flatten(msg) : `${field}: ${flatten(msg)}`))
    .join(" · ");
}

export default api;
