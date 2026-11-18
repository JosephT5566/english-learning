import { derived, get, writable } from "svelte/store";

export type SessionProfile = {
  id: number;
  email: string;
  name?: string;
  picture?: string;
};
export type AuthSession =
  | { kind: "initializing" }
  | { kind: "signed-out" }
  | { kind: "guest" }
  | { kind: "authenticated"; profile: SessionProfile }
  | { kind: "expired"; profile: SessionProfile | null };
export type AuthNotice =
  | null
  | { kind: "signing-in" }
  | { kind: "expired" }
  | { kind: "signed-out" }
  | { kind: "other-tab" }
  | { kind: "error"; email?: string }
  | { kind: "account-changed"; count: number; previousEmail?: string }
  | { kind: "saved"; count: number }
  | { kind: "pending-expired" };

export const authSession = writable<AuthSession>({ kind: "initializing" });
export const authOffline = writable<boolean>(false);
export const authNotice = writable<AuthNotice>(null);
export const signInOpen = writable(false);
export const isSignedIn = derived(
  authSession,
  (session) => session.kind === "authenticated",
);
export const canWrite = isSignedIn;

export function setSignIn(profile: SessionProfile) {
  authOffline.set(false);
  const current = get(authSession);
  if (
    current.kind !== "authenticated" ||
    JSON.stringify(current.profile) !== JSON.stringify(profile)
  )
    authSession.set({ kind: "authenticated", profile });
}
export function setSignOut() {
  authOffline.set(false);
  if (get(authSession).kind !== "signed-out")
    authSession.set({ kind: "signed-out" });
}
