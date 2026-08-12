import type { ComparePayload, RunPayload } from "./types";

const json = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
};

export const runSimulation = (scenario: string, controller: string, seed?: number) =>
  json<RunPayload>("/simulation/run", {
    method: "POST",
    body: JSON.stringify({ scenario, controller, seed }),
  });

export const compareSimulation = (scenario: string, seed?: number) =>
  json<ComparePayload>("/simulation/compare", {
    method: "POST",
    body: JSON.stringify({ scenario, seed }),
  });
