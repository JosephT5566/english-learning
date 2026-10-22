import { derived, get, writable } from "svelte/store";

export type SessionProfile = {
  name?: string;
  email?: string;
  picture?: string;
  sub?: string;
};
export type AuthSession =
  | { kind: "initializing" }
  | { kind: "signed-out" }
  | { kind: "guest" }
  | { kind: "authenticated"; profile: SessionProfile };

export const authSession = writable<AuthSession>({ kind: "initializing" });
export const isSignedIn = derived(
  authSession,
  (session) => session.kind === "authenticated",
);

export function setSignIn(profile: SessionProfile = {}) {
  const current = get(authSession);
  if (
    current.kind === "authenticated" &&
    JSON.stringify(current.profile) === JSON.stringify(profile)
  )
    return;
  authSession.set({ kind: "authenticated", profile });
}

export function setSignOut() {
  if (get(authSession).kind !== "signed-out")
    authSession.set({ kind: "signed-out" });
}
