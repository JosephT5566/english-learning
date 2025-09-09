<script lang="ts">
	import classNames from 'classnames';
	import type { Snippet } from 'svelte';
	import Icon from '@iconify/svelte';

	// Svelte 5 runes style
	interface Props {
		open?: boolean;
		title?: string;
		closeOnEsc?: boolean;
		closeOnBackdrop?: boolean;
		initialFocusSelector?: string;
		handleClose: () => void;
		ModalBody?: Snippet;
		ModalFooter?: Snippet;
	}

	let {
		open = false,
		title,
		closeOnEsc = true,
		closeOnBackdrop = true,
		initialFocusSelector,
		handleClose,
		ModalBody,
		ModalFooter,
	}: Props = $props();

	let dialogEl: HTMLDialogElement | null = null;
	let lastActive: Element | null = null;

	function lockScroll(lock: boolean) {
		const root = document.documentElement;
		if (lock) {
			const scrollBarWidth = window.innerWidth - document.documentElement.clientWidth;
			root.style.overflow = 'hidden';
			// 避免因隱藏滾動條造成抖動
			if (scrollBarWidth > 0) root.style.paddingRight = `${scrollBarWidth}px`;
		} else {
			root.style.overflow = '';
			root.style.paddingRight = '';
		}
	}

	function show() {
		if (!dialogEl) {
			return;
		}
		if (dialogEl.open) {
			return;
		}

		lastActive = document.activeElement;
		// 用 showModal() 會自帶「焦點陷阱」與 backdrop
		dialogEl.showModal();
		lockScroll(true);
		// 初始焦點
		queueMicrotask(() => {
			const target =
				(initialFocusSelector &&
					dialogEl!.querySelector<HTMLElement>(initialFocusSelector)) ||
				dialogEl!.querySelector<HTMLElement>('[data-autofocus]') ||
				dialogEl!;
			target?.focus();
		});
	}

	function hide() {
		if (!dialogEl) {
			return;
		}
		if (!dialogEl.open) {
			return;
		}

		dialogEl.close();
		lockScroll(false);
		(lastActive as HTMLElement | null)?.focus?.();
	}

	$effect(() => {
		if (typeof window === 'undefined') {
			return; // SSR 安全}
		}
		open ? show() : hide();
	});

	function onClose(e: Event) {
		// 使用者按 Esc 會觸發 cancel
		if (!closeOnEsc) {
			e.preventDefault();
			return;
		}
		handleClose();
	}

	function onBackdropClick(e: MouseEvent) {
		if (!closeOnBackdrop) {
			return;
		}
		if (e.target === dialogEl) {
			handleClose();
		}
	}
</script>

<dialog
	bind:this={dialogEl}
	class={classNames(
		'top-[50%]',
		'left-[50%]',
		'rounded-2xl',
		'translate-[-50%]',
		'p-0',
		'border-0',
		'max-w-[90vw]',
		'w-[640px]',
		'bg-transparent'
	)}
	aria-labelledby={title ? 'modal-title' : undefined}
	onclose={onClose}
	onclick={onBackdropClick}
>
	<!-- backdrop 樣式（原生 <dialog> 的 ::backdrop） -->
	<style>
		dialog::backdrop {
			background: rgba(0, 0, 0, 0.45);
			backdrop-filter: blur(2px);
		}
	</style>

	<!-- 內容卡片 -->
	<div
		class={classNames(
			'modal-content',
			'bg-white',
			'dark:bg-neutral-900',
			'rounded-2xl',
			'shadow-xl',
			'overflow-hidden'
		)}
	>
		<!-- Header -->
		<div
			class="modal-header flex items-center justify-between px-5 py-4 border-b border-black/5 dark:border-white/10"
		>
			<h2 id="modal-title" class="text-lg font-semibold">
				{title}
			</h2>
			<button
				type="button"
				class={classNames(
					'rounded-xl',
					'text-sm',
					'cursor-pointer',
					'text-rose-500',
					'hover:text-rose-700',
					'hover:bg-slate-100',
					'transition'
				)}
				aria-label="Close modal"
				onclick={onClose}
			>
				<Icon icon="solar:close-square-bold" width="32" height="32" />
			</button>
		</div>

		<!-- Body -->
		{#if ModalBody}
			<div class="modal-body px-5 py-4">
				{@render ModalBody()}
			</div>
		{/if}

		<!-- Footer -->
		{#if ModalFooter}
			<div
				class="modal-footer flex items-center justify-end gap-2 px-5 py-4 border-t border-black/5 dark:border-white/10"
			>
				{@render ModalFooter()}
			</div>
		{/if}
	</div>
</dialog>
