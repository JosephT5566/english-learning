import type { components } from './generated';

export type TargetLanguage = components['schemas']['Deck']['target_language'];
export type ReviewDecision = components['schemas']['ReviewSubmissionItem']['decision'];
export type ArchiveStatus = 'active' | 'archived';

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

export type ReviewState = components['schemas']['ReviewState'];
export type DeckSummary = components['schemas']['DeckSummary'];
export type Deck = components['schemas']['Deck'];
export type TagSummary = components['schemas']['TagSummary'];
export type CardSummary = components['schemas']['CardSummary'];
export type CardDetail = components['schemas']['CardDetail'];
export type DueCard = components['schemas']['DueCard'];
export type DeckCreate = components['schemas']['DeckCreate'];
export type DeckUpdate = components['schemas']['DeckUpdate'];
export type CardCreate = components['schemas']['CardCreate'];
export type CardUpdate = components['schemas']['CardUpdate'];

export interface Page<T> {
	items: T[];
	next_cursor: string | null;
}

export type ReviewSubmissionItem = components['schemas']['ReviewSubmissionItem'];
export type ReviewSubmission = components['schemas']['ReviewSubmission'];
export type TransitionState = components['schemas']['TransitionState'];
export type ReviewResultItem = components['schemas']['ReviewResultItem'];
export type ReviewResult = components['schemas']['ReviewResult'];

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
		typeof value.ease_factor === 'string' &&
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

export function isDeck(value: unknown): value is Deck {
	if (!isRecord(value) || !isDeckSummary(value)) return false;
	const record = value as Record<string, unknown>;
	return (
		Number.isInteger(record.version) &&
		Number(record.version) >= 1 &&
		typeof record.created_at === 'string' &&
		typeof record.updated_at === 'string'
	);
}

function isTagSummary(value: unknown): value is TagSummary {
	return isRecord(value) && typeof value.id === 'string' && typeof value.display_name === 'string';
}

function isCardSummary(value: unknown): value is CardSummary {
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
		typeof value.updated_at === 'string'
	);
}

export function isCardDetail(value: unknown): value is CardDetail {
	if (!isRecord(value) || !isCardSummary(value)) return false;
	const record = value as Record<string, unknown>;
	return (
		isNullableString(record.target_language_definition) &&
		isNullableString(record.example_sentence) &&
		isNullableString(record.example_translation) &&
		isNullableString(record.example_source) &&
		isStringArray(record.synonyms) &&
		isStringArray(record.antonyms) &&
		isNullableString(record.part_of_speech_detail) &&
		isNullableString(record.note) &&
		isNullableString(record.supplementary_note) &&
		isNullableString(record.learned_on) &&
		typeof record.created_at === 'string' &&
		Array.isArray(record.tags) &&
		record.tags.every(isTagSummary) &&
		(record.review_state === null || isReviewState(record.review_state))
	);
}

function isDueCard(value: unknown): value is DueCard {
	return isCardDetail(value) && isReviewState(value.review_state);
}

function isPageOf<T>(value: unknown, guard: (item: unknown) => item is T): value is Page<T> {
	if (!isRecord(value) || !Array.isArray(value.items)) return false;
	if (value.next_cursor !== null && typeof value.next_cursor !== 'string') return false;
	return value.items.every(guard);
}

export function isDeckPage(value: unknown): value is Page<Deck> {
	return isPageOf(value, isDeck);
}

export function isCardSummaryPage(value: unknown): value is Page<CardSummary> {
	return isPageOf(value, isCardSummary);
}

export function isDueCardPage(value: unknown): value is Page<DueCard> {
	return isPageOf(value, isDueCard);
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
				isReviewState(item.resulting_state),
		)
	);
}
