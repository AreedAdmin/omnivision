import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string;
export const SCHEMA = (import.meta.env.VITE_SUPABASE_SCHEMA as string) || "assemblyai";

export const supabase = createClient(url, key, { db: { schema: SCHEMA } });

export const SERVER_URL =
  (import.meta.env.VITE_SERVER_URL as string) || "http://localhost:8000";

export const WS_URL = SERVER_URL.replace(/^http/, "ws");
