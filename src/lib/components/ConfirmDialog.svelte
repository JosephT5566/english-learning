<script lang="ts">
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js';

	let {
		eyebrow,
		title,
		description,
		cancelLabel,
		confirmLabel,
		busyLabel = 'Working…',
		busy = false,
		oncancel,
		onconfirm,
	}: {
		eyebrow: string;
		title: string;
		description: string;
		cancelLabel: string;
		confirmLabel: string;
		busyLabel?: string;
		busy?: boolean;
		oncancel: () => void;
		onconfirm: () => void | Promise<void>;
	} = $props();

	function getOpen(): boolean {
		return true;
	}

	function setOpen(open: boolean): void {
		if (!open && !busy) oncancel();
	}
</script>

<AlertDialog.Root bind:open={getOpen, setOpen}>
	<AlertDialog.Content
		overlayClass="drawer-backdrop"
		class="confirm-card max-w-none gap-0 ring-0 sm:max-w-none"
		escapeKeydownBehavior={busy ? 'ignore' : 'close'}
	>
		<p class="management-eyebrow">{eyebrow}</p>
		<AlertDialog.Title>{title}</AlertDialog.Title>
		<AlertDialog.Description>{description}</AlertDialog.Description>
		<div class="form-actions">
			<AlertDialog.Cancel class="secondary-button h-auto" disabled={busy}>
				{cancelLabel}
			</AlertDialog.Cancel>
			<button class="danger-button" type="button" disabled={busy} onclick={onconfirm}>
				{busy ? busyLabel : confirmLabel}
			</button>
		</div>
	</AlertDialog.Content>
</AlertDialog.Root>
