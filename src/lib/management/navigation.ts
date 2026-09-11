import type { ArchiveStatus, TargetLanguage } from '$lib/api/contracts';

export type LanguageQuery =
	| { kind: 'missing'; language: 'en' }
	| { kind: 'invalid'; language: null }
	| { kind: 'valid'; language: TargetLanguage };

export function readLanguageQuery(searchParams: URLSearchParams): LanguageQuery {
	const value = searchParams.get('language');
	if (value === null) return { kind: 'missing', language: 'en' };
	if (value === 'en' || value === 'ja') return { kind: 'valid', language: value };
	return { kind: 'invalid', language: null };
}

export function readArchiveStatus(searchParams: URLSearchParams): ArchiveStatus {
	return searchParams.get('status') === 'archived' ? 'archived' : 'active';
}

export function languageName(language: TargetLanguage): string {
	return language === 'ja' ? 'Japanese' : 'English';
}
