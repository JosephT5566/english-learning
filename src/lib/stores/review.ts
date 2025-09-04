import { writable } from 'svelte/store';
import type { WordItem, UpdateFields } from '$lib/types';
import { STAGE_INTERVALS } from '$lib/utils';

export const wordList = writable<WordItem[]>(undefined);
export const currentIdx = writable(0);
export const newFields = writable<UpdateFields>({});

// export function nextQuestion(loopWrongAgain = true) {
export function nextQuestion() {
	currentIdx.update((i) => i + 1);
}

export function restartWithWrongs(wrongs: WordItem[]) {
	wordList.set(wrongs);
	currentIdx.set(0);
}

export function setNewField(id: number, newStage: number, newEaseFactor: number) {
  const today = new Date();
  const nextDay = new Date(today);
  const newIntervalDays = Math.round((STAGE_INTERVALS[newStage] * newEaseFactor));

  // today add newIntervalDays
  nextDay.setDate(today.getDate() + newIntervalDays);

	newFields.update((fields) => ({
		...fields,
		[id]: {
			lastReview: today, // update to now
			nextReview: nextDay,
			reviewStage: newStage,
			easeFactor: newEaseFactor,
		},
	}));
}
