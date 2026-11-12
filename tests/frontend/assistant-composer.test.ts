import { describe, expect, it } from "vitest";
import { shouldSendOnEnter } from "$lib/assistant/composer";

describe("assistant composer keyboard", () => {
  const enter = {
    key: "Enter",
    shiftKey: false,
    isComposing: false,
    keyCode: 13,
  };
  it("sends on Enter and keeps Shift+Enter as a newline", () => {
    expect(shouldSendOnEnter(enter, false)).toBe(true);
    expect(shouldSendOnEnter({ ...enter, shiftKey: true }, false)).toBe(false);
    expect(shouldSendOnEnter({ ...enter, key: "a" }, false)).toBe(false);
  });
  it("never sends an IME candidate confirmation", () => {
    expect(shouldSendOnEnter({ ...enter, isComposing: true }, false)).toBe(
      false,
    );
    expect(shouldSendOnEnter({ ...enter, keyCode: 229 }, false)).toBe(false);
    expect(shouldSendOnEnter(enter, true)).toBe(false);
    expect(shouldSendOnEnter(enter, false)).toBe(true);
  });
});
