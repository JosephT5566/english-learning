<script lang="ts">
	import { Dialog } from 'bits-ui';
	import XIcon from '@lucide/svelte/icons/x';
	import type { Snippet } from 'svelte';

	let {
		title,
		dismissible = true,
		onclose,
		children,
	}: {
		title: string;
		dismissible?: boolean;
		onclose: () => void;
		children: Snippet;
	} = $props();

	// These dialogs are mounted by page state, without a primitive Trigger.
	const returnFocus = typeof document === 'undefined' ? null : document.activeElement;
	function getOpen(): boolean {
		return true;
	}
	function setOpen(open: boolean): void {
		if (!open && dismissible) onclose();
	}
</script>

<Dialog.Root bind:open={getOpen, setOpen}>
	<Dialog.Portal>
		<Dialog.Overlay class="drawer-backdrop" />
		<Dialog.Content
			class="card-dialog"
			data-slot="card-dialog"
			escapeKeydownBehavior={dismissible ? 'close' : 'ignore'}
			interactOutsideBehavior={dismissible ? 'close' : 'ignore'}
			onCloseAutoFocus={(event) => {
				event.preventDefault();
				if (returnFocus instanceof HTMLElement && returnFocus.isConnected) returnFocus.focus();
			}}
		>
			<header>
				<Dialog.Title class="card-dialog-title">{title}</Dialog.Title>
				<Dialog.Description class="visually-hidden">
					Review your card details before saving.
				</Dialog.Description>
				<Dialog.Close
					type="button"
					class="icon-button"
					aria-label="Close"
					disabled={!dismissible}
					title="Close"><XIcon size={20} aria-hidden="true" /></Dialog.Close
				>
			</header>
			<div class="card-dialog-body">{@render children()}</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<style>
	:global(.card-dialog) {
		position: fixed;
		z-index: 51;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		display: flex;
		flex-direction: column;
		width: min(60rem, calc(100vw - 3rem));
		max-height: calc(100dvh - 3rem);
		box-sizing: border-box;
		overflow: hidden;
		border: 1px solid rgba(64, 117, 166, 0.25);
		border-radius: 1.25rem;
		background: #edf3f8;
		box-shadow: 0 24px 70px rgba(31, 57, 79, 0.24);
		outline: none;
	}
	header {
		display: flex;
		flex-shrink: 0;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1.1rem 1.5rem;
		border-bottom: 1px solid rgba(64, 117, 166, 0.2);
	}
	:global(.card-dialog-title) {
		margin: 0;
		font-family: 'Bodoni Moda', Georgia, serif;
		font-size: 1.65rem;
	}
	.card-dialog-body {
		min-height: 0;
		min-width: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 1.5rem;
	}
	:global(.card-dialog .icon-button) {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.75rem;
		height: 2.75rem;
		padding: 0;
		flex-shrink: 0;
	}
	@media (max-width: 640px) {
		:global(.card-dialog) {
			inset: 0;
			transform: none;
			width: 100%;
			height: 100dvh;
			max-height: 100dvh;
			border: 0;
			border-radius: 0;
		}
		header {
			padding: max(1rem, env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right)) 1rem
				max(1rem, env(safe-area-inset-left));
		}
		.card-dialog-body {
			flex: 1;
			padding: 1rem max(1rem, env(safe-area-inset-right)) max(1rem, env(safe-area-inset-bottom))
				max(1rem, env(safe-area-inset-left));
		}
	}
</style>
