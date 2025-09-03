export type StudyDirection = 'EN_ZH' | 'ZH_EN';

export type ReviewStage = 1 | 2 | 3 | 4 | 5;

export interface WordItem {
	id: string;
	lessonDate: string; // ISO
	content: string;
	type: string; // vocabulary, phrase, ...
	phonics?: string; // 音標
	chineseExplain: string;
	engExplain?: string;
	tags?: string; // 逗號分隔；要改成 string[] 也可
	supplementary?: string;
	status?: string; // active, deleted
	example?: string;
	synonyms?: string; // 逗號分隔；要改成 string[] 也可
	antonyms?: string;
	note?: string;
	reviewStage: ReviewStage;
	easeFactor: number; // 1.3 ~ 2.5
	intervalDays: number; // 間隔天數
	lastReview?: string; // ISO
	nextReview?: string; // ISO
	createdDate?: string; // ISO
}

export type UpdateFields = Record<
	string,
	{ reviewStage: number; lastReview: Date; nextReview: Date; easeFactor: number }
>;

// 可重用的 App Script 回應型別
export type AppScriptResponse<T, E = string> = { ok: true; result: T } | { ok: false; error?: E };

export type SuccessResponse<T> = Extract<AppScriptResponse<T>, { ok: true }>;
export type FailureResponse<E = string> = Extract<AppScriptResponse<never, E>, { ok: false }>;

// type guard
export const isSuccess = <T, E = string>(r: AppScriptResponse<T, E>): r is SuccessResponse<T> =>
	r.ok;
export const isFailure = <T, E = string>(r: AppScriptResponse<T, E>): r is FailureResponse<E> =>
	!r.ok;

// 以泛型回應取代原本的特定回應
export type WordListResponse = AppScriptResponse<WordItem[]>;
export type ErrorResponse = FailureResponse;
