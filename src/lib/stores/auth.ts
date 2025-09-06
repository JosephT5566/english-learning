import { writable } from 'svelte/store';

export const isSignedIn = writable<boolean>(false);

export function setSignIn() {
    isSignedIn.set(true);
}