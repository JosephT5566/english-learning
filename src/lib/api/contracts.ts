export type TargetLanguage = 'en' | 'ja';
export type ReviewDecision = 'no' | 'no_a_bit' | 'yes_a_bit' | 'yes';

export interface ApiErrorBody {
	code: string;
	message: string;
	retryable: boolean;
	request_id: string;
	details?: Record<string, unknown>;
}

export interface ApiErrorEnvelope {
	error: ApiErrorBody;
}

export interface ReviewState {
	review_stage: number;
	ease_factor: string | number;
	interval_days: number;
	last_reviewed_at: string | null;
	next_review_at: string;
	version: number;
}

export interface DeckSummary {
	id: string;
	title: string;
	target_language: TargetLanguage;
	explanation_language: 'en' | 'ja' | 'zh-TW';
	archived_at: string | null;
}

export interface TagSummary {
	id: string;
	display_name: string;
}

export interface DueCard {
	id: string;
	deck: DeckSummary;
	term: string;
	meaning: string;
	reading: string | null;
	pronunciation: string | null;
	romanization: string | null;
	part_of_speech: string | null;
	archived_at: string | null;
	version: number;
	updated_at: string;
	target_language_definition: string | null;
	example_sentence: string | null;
	example_translation: string | null;
	example_source: string | null;
	synonyms: string[];
	antonyms: string[];
	part_of_speech_detail: string | null;
	note: string | null;
	supplementary_note: string | null;
	learned_on: string | null;
	created_at: string;
	tags: TagSummary[];
	review_state: ReviewState;
}

export interface Page<T> {
	items: T[];
	next_cursor: string | null;
}

export interface ReviewSubmissionItem {
	card_id: string;
	decision: ReviewDecision;
	expected_version: number;
}

export interface ReviewSubmission {
	items: ReviewSubmissionItem[];
}

export type TransitionState = ReviewState;

export interface ReviewResultItem {
	event_id: number;
	card_id: string;
	decision: ReviewDecision;
	quality: number;
	previous_state: TransitionState;
	resulting_state: TransitionState;
}

export interface ReviewResult {
	batch_id: string;
	reviewed_at: string;
	algorithm_version: string;
	items: ReviewResultItem[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
	return value === null || typeof value === 'string';
}

function isStringArray(value: unknown): value is string[] {
	return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isReviewDecision(value: unknown): value is ReviewDecision {
	return value === 'no' || value === 'no_a_bit' || value === 'yes_a_bit' || value === 'yes';
}

export function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
	if (!isRecord(value) || !isRecord(value.error)) return false;
	const error = value.error;
	return (
		typeof error.code === 'string' &&
		typeof error.message === 'string' &&
		typeof error.retryable === 'boolean' &&
		typeof error.request_id === 'string' &&
		(error.details === undefined || isRecord(error.details))
	);
}

function isReviewState(value: unknown): value is ReviewState {
	if (!isRecord(value)) return false;
	return (
		Number.isInteger(value.review_stage) &&
		Number(value.review_stage) >= 1 &&
		Number(value.review_stage) <= 5 &&
		(typeof value.ease_factor === 'string' || typeof value.ease_factor === 'number') &&
		Number.isInteger(value.interval_days) &&
		Number(value.interval_days) >= 0 &&
		isNullableString(value.last_reviewed_at) &&
		typeof value.next_review_at === 'string' &&
		Number.isInteger(value.version) &&
		Number(value.version) >= 1
	);
}

function isDeckSummary(value: unknown): value is DeckSummary {
	if (!isRecord(value)) return false;
	return (
		typeof value.id === 'string' &&
		typeof value.title === 'string' &&
		(value.target_language === 'en' || value.target_language === 'ja') &&
		(value.explanation_language === 'en' ||
			value.explanation_language === 'ja' ||
			value.explanation_language === 'zh-TW') &&
		isNullableString(value.archived_at)
	);
}

function isTagSummary(value: unknown): value is TagSummary {
	return isRecord(value) && typeof value.id === 'string' && typeof value.display_name === 'string';
}

function isDueCard(value: unknown): value is DueCard {
	if (!isRecord(value)) return false;
	return (
		typeof value.id === 'string' &&
		isDeckSummary(value.deck) &&
		typeof value.term === 'string' &&
		typeof value.meaning === 'string' &&
		isNullableString(value.reading) &&
		isNullableString(value.pronunciation) &&
		isNullableString(value.romanization) &&
		isNullableString(value.part_of_speech) &&
		isNullableString(value.archived_at) &&
		Number.isInteger(value.version) &&
		typeof value.updated_at === 'string' &&
		isNullableString(value.target_language_definition) &&
		isNullableString(value.example_sentence) &&
		isNullableString(value.example_translation) &&
		isNullableString(value.example_source) &&
		isStringArray(value.synonyms) &&
		isStringArray(value.antonyms) &&
		isNullableString(value.part_of_speech_detail) &&
		isNullableString(value.note) &&
		isNullableString(value.supplementary_note) &&
		isNullableString(value.learned_on) &&
		typeof value.created_at === 'string' &&
		Array.isArray(value.tags) &&
		value.tags.every(isTagSummary) &&
		isReviewState(value.review_state)
	);
}

export function isDueCardPage(value: unknown): value is Page<DueCard> {
	if (!isRecord(value) || !Array.isArray(value.items)) return false;
	if (value.next_cursor !== null && typeof value.next_cursor !== 'string') return false;
	return value.items.every(isDueCard);
}

export function isReviewResult(value: unknown): value is ReviewResult {
	return (
		isRecord(value) &&
		typeof value.batch_id === 'string' &&
		typeof value.reviewed_at === 'string' &&
		typeof value.algorithm_version === 'string' &&
		Array.isArray(value.items) &&
		value.items.every(
			(item) =>
				isRecord(item) &&
				Number.isInteger(item.event_id) &&
				typeof item.card_id === 'string' &&
				isReviewDecision(item.decision) &&
				Number.isInteger(item.quality) &&
				isReviewState(item.previous_state) &&
				isReviewState(item.resulting_state)
		)
	);
}
