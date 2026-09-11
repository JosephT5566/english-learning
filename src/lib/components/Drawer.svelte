<script lang="ts">
	import * as Sheet from '$lib/components/ui/sheet/index.js';
	import type { Snippet } from 'svelte';

	let {
		title,
		wide = false,
		dismissible = true,
		onclose,
		children,
	}: {
		title: string;
		wide?: boolean;
		dismissible?: boolean;
		onclose: () => void;
		children: Snippet;
	} = $props();

	function getOpen(): boolean {
		return true;
	}

	function setOpen(open: boolean): void {
		if (!open && dismissible) onclose();
	}
</script>

<Sheet.Root bind:open={getOpen, setOpen}>
	<Sheet.Content
		overlayClass="drawer-backdrop"
		showCloseButton={false}
		class={`drawer w-auto max-w-none gap-0 text-base sm:max-w-none${wide ? ' wide' : ''}`}
		escapeKeydownBehavior={dismissible ? 'close' : 'ignore'}
		interactOutsideBehavior={dismissible ? 'close' : 'ignore'}
	>
		<header>
			<Sheet.Title class="drawer-title">{title}</Sheet.Title>
			<Sheet.Description class="visually-hidden">
				Manage {title.toLocaleLowerCase()} in this panel.
			</Sheet.Description>
			<Sheet.Close type="button" class="icon-button" aria-label="Close" disabled={!dismissible}
				>×</Sheet.Close
			>
		</header>
		<div class="drawer-body">{@render children()}</div>
	</Sheet.Content>
</Sheet.Root>
