// Quality flags for the Stops/Routes panels ("No trips", "Off shape",
// "No shape") need joins the frontend does not have; this asks the
// stubbed /api/quality/* endpoints once and remembers that the backend
// does not serve them yet, so the chips can disable themselves honestly.
import { api } from "./api.js";

const cache = {};

export async function fetchQuality(kind) {
  if (kind in cache) return cache[kind];
  try {
    cache[kind] = await api("GET", `/api/quality/${kind}`);
  } catch (error) {
    cache[kind] = null; // pending backend support
  }
  return cache[kind];
}
