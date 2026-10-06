import Ajv2020, { type ErrorObject } from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import schema from '$lib/api/card-drafts.schema.json';
import { CARD_OPTIONAL_TEXT_FIELDS, parseCardJson } from './json-cards';

const ajv = new Ajv2020({ allErrors: true, strictRequired: false });
addFormats(ajv, { formats: ['date'], mode: 'full' });
const validate = ajv.compile(schema);

export type LocalJsonValidation =
	| { valid: true; value: unknown; messages: [] }
	| { valid: false; messages: string[] };

function isRecord(value: unknown): value is Record<string, unknown> {
	return !!value && typeof value === 'object' && !Array.isArray(value);
}

// Pydantic trims constrained content strings before checking lengths. Leave enums and dates alone.
function normalizedContent(value: unknown): unknown {
	if (!isRecord(value) || !Array.isArray(value.cards)) return value;
	return {
		...value,
		cards: value.cards.map((card) => {
			if (!isRecord(card)) return card;
			const fields = { ...card };
			for (const key of ['term', 'meaning', ...CARD_OPTIONAL_TEXT_FIELDS]) {
				if (key !== 'learned_on' && typeof fields[key] === 'string')
					fields[key] = fields[key].trim();
			}
			for (const key of ['synonyms', 'antonyms']) {
				if (Array.isArray(fields[key]))
					fields[key] = fields[key].map((word: unknown) =>
						typeof word === 'string' ? word.trim() : word,
					);
			}
			return fields;
		}),
	};
}

function errorMessage(error: ErrorObject): string | null {
	// Leaf errors describe nullable unions and conditional failures more clearly than summary errors.
	if (['anyOf', 'if'].includes(error.keyword)) return null;
	const parts = error.instancePath
		.split('/')
		.slice(1)
		.map((part) => part.replaceAll('~1', '/').replaceAll('~0', '~'));
	if (error.keyword === 'required') parts.push(error.params.missingProperty);
	if (error.keyword === 'additionalProperties') parts.push(error.params.additionalProperty);
	const label =
		parts[0] === 'cards' && /^\d+$/.test(parts[1] ?? '')
			? `Card ${Number(parts[1]) + 1}${parts.length > 2 ? ` · ${parts.slice(2).join('.')}` : ''}`
			: parts.join('.') || 'JSON';
	const descriptions: Record<string, string> = {
		required: 'This field is required.',
		additionalProperties: 'Remove this unsupported field.',
		minLength: 'Enter a nonblank value.',
		maxLength: `Use at most ${error.params.limit} characters.`,
		minItems: `Include at least ${error.params.limit} item(s).`,
		maxItems: `Include at most ${error.params.limit} item(s).`,
		enum: 'Select a supported value.',
		format: 'Use a valid date in YYYY-MM-DD format.',
		type: `Expected ${error.params.type}.`,
	};
	const detail = descriptions[error.keyword] ?? 'Check this value.';
	return `${label}: ${detail}`;
}

export function validateCardJson(source: string): LocalJsonValidation {
	try {
		const value = normalizedContent(parseCardJson(source));
		if (validate(value)) return { valid: true, value, messages: [] };
		const errors = validate.errors ?? [];
		// For a nullable field with a wrong value, skip the irrelevant "expected null" branch.
		const messages = [
			...new Set(
				errors
					.filter((error) => !(error.keyword === 'type' && error.params.type === 'null'))
					.map(errorMessage)
					.filter((message): message is string => message !== null),
			),
		];
		return { valid: false, messages: messages.slice(0, 30) };
	} catch (cause) {
		return {
			valid: false,
			messages: [cause instanceof Error ? cause.message : 'Check the JSON input.'],
		};
	}
}
