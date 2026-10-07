import Ajv2020, { type ErrorObject } from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { findNodeAtLocation, parseTree, type Node, type ParseError } from 'jsonc-parser';
import schema from '$lib/api/card-drafts.schema.json';
import { CARD_OPTIONAL_TEXT_FIELDS, JSON_BYTE_LIMIT, parseCardJson } from './json-cards';

const ajv = new Ajv2020({ allErrors: true, strictRequired: false });
addFormats(ajv, { formats: ['date'], mode: 'full' });
const validate = ajv.compile(schema);

export type JsonErrorLocation = {
	offset: number;
	length: number;
	line: number;
	column: number;
};
export type JsonIssue = { message: string; location?: JsonErrorLocation };

function location(source: string, offset: number, length: number): JsonErrorLocation {
	const lines = source.slice(0, offset).split(/\r\n|\r|\n/);
	return {
		offset,
		length,
		line: lines.length,
		column: lines.at(-1)!.length + 1,
	};
}

function sourceTree(source: string, errors: ParseError[] = []): Node | undefined {
	try {
		return parseTree(source, errors, { disallowComments: true, allowTrailingComma: false });
	} catch {
		// Deeply nested untrusted input may exceed the parser's stack. Keep validation errors usable.
		return undefined;
	}
}

function issueLocation(
	source: string,
	tree: Node | undefined,
	error: ErrorObject,
): JsonErrorLocation | undefined {
	if (!tree) return;
	const path = error.instancePath
		.split('/')
		.slice(1)
		.map((part) => part.replaceAll('~1', '/').replaceAll('~0', '~'));
	if (error.keyword === 'additionalProperties') path.push(error.params.additionalProperty);
	let node: Node | undefined = tree;
	for (const part of path) {
		if (!node) break;
		node = findNodeAtLocation(node, [node.type === 'array' ? Number(part) : part]);
	}
	if (!node) return;
	// Missing fields point to their containing object rather than inventing a text range.
	return location(source, node.offset, error.keyword === 'required' ? 1 : node.length);
}

export type LocalJsonValidation =
	| { valid: true; value: unknown; messages: [] }
	| { valid: false; messages: string[]; issues?: JsonIssue[] };

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
		const tree = sourceTree(source);
		const issues: JsonIssue[] = [];
		for (const error of errors) {
			if (error.keyword === 'type' && error.params.type === 'null') continue;
			const message = errorMessage(error);
			if (!message || issues.some((issue) => issue.message === message)) continue;
			issues.push({ message, location: issueLocation(source, tree, error) });
			if (issues.length === 30) break;
		}
		return {
			valid: false,
			messages: issues.map((issue) => issue.message),
			issues,
		};
	} catch (cause) {
		const message = cause instanceof Error ? cause.message : 'Check the JSON input.';
		const errors: ParseError[] = [];
		// Do not parse oversized input a second time just to provide a location.
		if (new TextEncoder().encode(source).length <= JSON_BYTE_LIMIT) sourceTree(source, errors);
		const first = errors[0];
		return {
			valid: false,
			messages: [message],
			issues: [
				{
					message,
					location: first ? location(source, first.offset, first.length) : undefined,
				},
			],
		};
	}
}
