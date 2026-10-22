import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";
import AccountMenu from "$lib/components/AccountMenu.svelte";
import type { ComponentProps } from "svelte";

function setup(props: Partial<ComponentProps<typeof AccountMenu>> = {}) {
  const onSignIn = vi.fn();
  const onSignOut = vi.fn();
  const view = render(AccountMenu, { onSignIn, onSignOut, ...props });
  return { ...view, onSignIn, onSignOut };
}

describe("Account menu", () => {
  it("shows guest identity and requests sign in only after selecting its action", async () => {
    const { onSignIn, onSignOut } = setup();
    const trigger = screen.getByRole("button", { name: "Guest account menu" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await fireEvent.click(trigger);
    expect(await screen.findByRole("menu", { name: "Account" })).toBeVisible();
    expect(screen.getByText("Guest")).toBeVisible();
    expect(
      screen.queryByRole("menuitem", { name: "Public practice" }),
    ).not.toBeInTheDocument();
    expect(onSignIn).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole("menuitem", { name: "Sign in" }));
    expect(onSignIn).toHaveBeenCalledOnce();
    expect(onSignOut).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByRole("menu")).not.toBeInTheDocument(),
    );
  });

  it("shows signed-in profile and invokes sign out", async () => {
    const { onSignIn, onSignOut } = setup({
      profile: { name: "Alex Chen", email: "alex@example.test" },
    });
    const trigger = screen.getByRole("button", {
      name: "Account menu for Alex Chen",
    });
    expect(trigger).toHaveTextContent("AC");
    await fireEvent.click(trigger);
    expect(await screen.findByText("alex@example.test")).toBeVisible();
    await fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledOnce();
    expect(onSignIn).not.toHaveBeenCalled();
  });

  it("falls back to initials when the avatar picture cannot load", async () => {
    const { container, rerender } = setup({
      profile: {
        name: "Alex Chen",
        picture: "https://example.test/avatar.png",
      },
    });
    const picture = container.querySelector("img");
    if (!picture) throw new Error("Expected profile picture");
    expect(picture).toHaveAttribute("referrerpolicy", "no-referrer");
    await fireEvent.error(picture);
    expect(container.querySelector("img")).not.toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveTextContent("AC");
    await rerender({
      profile: { name: "Alex Chen", picture: "https://example.test/new.png" },
    });
    expect(container.querySelector("img")).toHaveAttribute(
      "src",
      "https://example.test/new.png",
    );
  });

  it("supports keyboard selection without sending keys to background review handlers", async () => {
    const { onSignIn } = setup();
    const backgroundKeydown = vi.fn();
    window.addEventListener("keydown", backgroundKeydown);
    try {
      const trigger = screen.getByRole("button", {
        name: "Guest account menu",
      });
      trigger.focus();
      await fireEvent.keyDown(trigger, { key: "ArrowDown" });
      const item = await screen.findByRole("menuitem", { name: "Sign in" });
      item.focus();
      await fireEvent.keyDown(item, { key: "Enter" });
      expect(onSignIn).toHaveBeenCalledOnce();
      expect(backgroundKeydown).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("keydown", backgroundKeydown);
    }
  });

  it("closes after an outside pointer interaction", async () => {
    const { onSignIn, onSignOut } = setup();
    const trigger = screen.getByRole("button", { name: "Guest account menu" });
    await fireEvent.click(trigger);
    await screen.findByRole("menu", { name: "Account" });
    await fireEvent.pointerDown(document.body, {
      button: 0,
      clientX: 500,
      clientY: 500,
    });
    await waitFor(() =>
      expect(screen.queryByRole("menu")).not.toBeInTheDocument(),
    );
    expect(onSignIn).not.toHaveBeenCalled();
    expect(onSignOut).not.toHaveBeenCalled();
  });

  it("closes on Escape and returns focus to the avatar", async () => {
    setup();
    const trigger = screen.getByRole("button", { name: "Guest account menu" });
    await fireEvent.click(trigger);
    const item = await screen.findByRole("menuitem", { name: "Sign in" });
    item.focus();
    await fireEvent.keyDown(item, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("menu")).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
