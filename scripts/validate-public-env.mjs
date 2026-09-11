const requiredVariables = [
	'PUBLIC_API_BASE_URL',
	'PUBLIC_GOOGLE_AUTH_CLIENT_ID',
	'PUBLIC_EMAIL_WHITE_LIST',
];

const missingVariables = requiredVariables.filter((name) => !process.env[name]?.trim());

if (missingVariables.length > 0) {
	console.error(`Missing required public runtime configuration: ${missingVariables.join(', ')}`);
	process.exit(1);
}

let apiUrl;
try {
	apiUrl = new URL(process.env.PUBLIC_API_BASE_URL);
} catch {
	console.error('PUBLIC_API_BASE_URL must be an absolute URL');
	process.exit(1);
}

if (apiUrl.protocol !== 'https:') {
	console.error('PUBLIC_API_BASE_URL must use HTTPS for deployment');
	process.exit(1);
}

if (apiUrl.username || apiUrl.password || apiUrl.search || apiUrl.hash) {
	console.error('PUBLIC_API_BASE_URL must not contain credentials, a query, or a fragment');
	process.exit(1);
}
