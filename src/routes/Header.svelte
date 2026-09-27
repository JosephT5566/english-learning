<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { browser } from '$app/environment';

	let language = $derived(browser && page.url.searchParams.get('language') === 'ja' ? 'ja' : 'en');
	let homePath = $derived(resolve('/'));
	let reviewPath = $derived(resolve('/review'));
	let decksPath = $derived(resolve('/decks'));
	let searchPath = $derived(resolve('/search'));
</script>

<header>
	<nav aria-label="Primary navigation">
		<ul>
			<li>
				<a href={homePath} aria-current={page.url.pathname === homePath ? 'page' : undefined}
					>Home</a
				>
			</li>
			<li>
				<a
					href={reviewPath}
					aria-current={page.url.pathname === reviewPath ? 'page' : undefined}>Review</a
				>
			</li>
			<li>
				<a
					href={`${decksPath}?language=${language}`}
					aria-current={page.url.pathname.startsWith(decksPath) ||
					page.url.pathname.includes('/cards/')
						? 'page'
						: undefined}>Decks</a
				>
			</li>
			<li>
				<a
					href={searchPath}
					aria-current={page.url.pathname === searchPath ? 'page' : undefined}>Search</a
				>
			</li>
		</ul>
	</nav>
</header>

<style>
	header {
		position: relative;
		z-index: 10;
		display: flex;
		justify-content: center;
		padding: 0.75rem 1rem 0.25rem;
	}

	nav {
		display: flex;
		justify-content: center;
		border: 1px solid rgba(64, 117, 166, 0.16);
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.72);
		box-shadow: 0 6px 20px rgba(47, 78, 105, 0.08);
	}

	ul {
		display: flex;
		align-items: center;
		min-height: 3rem;
		padding: 0.25rem;
		margin: 0;
		list-style: none;
	}

	li {
		display: flex;
	}

	nav a {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 2.5rem;
		padding: 0 0.85rem;
		border-radius: 999px;
		color: #405c73;
		font-weight: 700;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		text-decoration: none;
		transition:
			color 160ms ease-out,
			background-color 160ms ease-out;
	}

	nav a:hover {
		color: #264f73;
		background: rgba(64, 117, 166, 0.1);
		text-decoration: none;
	}

	nav a[aria-current='page'] {
		color: white;
		background: #4075a6;
	}

	nav a:focus-visible {
		outline: 3px solid rgba(64, 117, 166, 0.32);
		outline-offset: 2px;
	}

	@media (max-width: 30rem) {
		header {
			padding-inline: 0.75rem;
		}

		nav,
		ul {
			width: 100%;
		}

		li {
			flex: 1;
		}

		nav a {
			width: 100%;
			padding-inline: 0.4rem;
			font-size: 0.68rem;
			letter-spacing: 0.07em;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		nav a {
			transition: none;
		}
	}
</style>
