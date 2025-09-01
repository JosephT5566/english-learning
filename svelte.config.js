import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const dev = process.argv.includes('dev');

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),

	kit: {
		adapter: adapter({
			// SPA 模式需要 fallback
			pages: 'build',
			assets: 'build',
			precompress: false,
			strict: true,
			fallback: 'index.html'
		}),
		paths: {
			// GH Pages 子路徑，請改成你的 repo 名稱
			base: dev ? '' : '/my-vocab'
		},
		// SPA：不預先產生各 route 的靜態檔，只輸出 index.html 作為 fallback
		// prerender: { entries: [] }
	}
};

export default config;
