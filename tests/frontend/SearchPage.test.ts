import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authSession } from "$lib/stores/auth";
import { ApiClientError } from "$lib/api/client";

import SearchPage from "../../src/routes/search/+page.svelte";

const api = vi.hoisted(() => ({
  keywordSearch: vi.fn(),
  semanticSearch: vi.fn(),
  getGenAIConsent: vi.fn(),
  grantGenAIConsent: vi.fn(),
  withdrawGenAIConsent: vi.fn(),
}));

vi.mock("$env/dynamic/public", () => ({ env: {} }));

vi.mock("$lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/api/client")>()),
  keywordSearch: api.keywordSearch,
  semanticSearch: api.semanticSearch,
  getGenAIConsent: api.getGenAIConsent,
  grantGenAIConsent: api.grantGenAIConsent,
  withdrawGenAIConsent: api.withdrawGenAIConsent,
}));

const japaneseCard = {
  id: "20000000-0000-0000-0000-000000000002",
  deck: {
    id: "10000000-0000-0000-0000-000000000002",
    title: "Japanese",
    target_language: "ja",
    explanation_language: "zh-TW",
    archived_at: null,
  },
  term: "勉強",
  meaning: "學習",
  reading: "べんきょう",
  pronunciation: null,
  romanization: "benkyou",
  part_of_speech: "noun",
  archived_at: null,
  version: 1,
  updated_at: "2026-09-01T00:00:00Z",
};

describe("Search page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authSession.set({ kind: "authenticated", profile: { sub: "owner-a" } });
    api.getGenAIConsent.mockResolvedValue({
      genai_consent_at: "2026-11-05T00:00:00Z",
    });
    api.grantGenAIConsent.mockResolvedValue({
      genai_consent_at: "2026-11-05T00:00:00Z",
    });
    api.withdrawGenAIConsent.mockResolvedValue({ genai_consent_at: null });
    api.keywordSearch.mockReset();
    api.semanticSearch.mockReset();
    api.keywordSearch.mockResolvedValue({
      items: [japaneseCard],
      next_cursor: null,
    });
    api.semanticSearch.mockResolvedValue({
      items: [],
      index_status: "complete",
      eligible_count: 1,
      indexed_count: 1,
    });
  });

  it("defaults to multilingual keyword search and labels Japanese results", async () => {
    render(SearchPage);

    expect(
      screen.getByRole("button", { name: "Words & phrases" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.queryByText(/Meaning search currently uses English cards only/),
    ).not.toBeInTheDocument();

    await fireEvent.input(
      screen.getByLabelText("Word, phrase, or translation"),
      {
        target: { value: "benkyou" },
      },
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search cards" }));

    await waitFor(() =>
      expect(api.keywordSearch).toHaveBeenCalledWith("benkyou"),
    );
    expect(screen.getByText("勉強")).toBeInTheDocument();
    expect(screen.getByText("JP")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /勉強/ })).toHaveAttribute(
      "href",
      "/cards/20000000-0000-0000-0000-000000000002?language=ja",
    );
    expect(api.semanticSearch).not.toHaveBeenCalled();
    expect(api.getGenAIConsent).not.toHaveBeenCalled();
    expect(api.grantGenAIConsent).not.toHaveBeenCalled();
  });

  it("preserves the query when switching to English-only semantic search", async () => {
    render(SearchPage);
    const input = screen.getByLabelText("Word, phrase, or translation");
    await fireEvent.input(input, { target: { value: "a lucky discovery" } });

    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    await waitFor(() => expect(api.getGenAIConsent).toHaveBeenCalled());

    expect(
      screen.getByText("Meaning search currently uses English cards only."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Describe the meaning or idea")).toHaveValue(
      "a lucky discovery",
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search cards" }));

    await waitFor(() =>
      expect(api.semanticSearch).toHaveBeenCalledWith({
        query: "a lucky discovery",
        target_language: "en",
        limit: 10,
      }),
    );
    expect(api.keywordSearch).not.toHaveBeenCalled();
  });

  it("offers an exact-word fallback when meaning search has no matches", async () => {
    api.semanticSearch.mockResolvedValue({
      items: [],
      index_status: "empty",
      eligible_count: 2,
      indexed_count: 0,
    });
    render(SearchPage);

    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    await waitFor(() => expect(api.getGenAIConsent).toHaveBeenCalled());
    await fireEvent.input(
      screen.getByLabelText("Describe the meaning or idea"),
      {
        target: { value: "a calm feeling" },
      },
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search cards" }));

    await waitFor(() =>
      expect(screen.getByText("No related cards found")).toBeInTheDocument(),
    );
    await fireEvent.click(
      screen.getByRole("button", { name: "Use words & phrases" }),
    );

    expect(screen.getByLabelText("Word, phrase, or translation")).toHaveValue(
      "a calm feeling",
    );
  });
  it("explains the content and provider and blocks meaning search until consent is granted", async () => {
    api.getGenAIConsent.mockResolvedValue({ genai_consent_at: null });
    render(SearchPage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    const grant = await screen.findByRole("button", { name: "Grant consent" });
    expect(
      screen.getByText(
        "Your card text and search queries are sent to Google Vertex AI for semantic search. You can withdraw consent here at any time.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Allow AI meaning search?" }),
    ).toBeVisible();
    expect(
      screen.queryByLabelText("Describe the meaning or idea"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Search cards" }),
    ).not.toBeInTheDocument();
    await fireEvent.click(screen.getByText("Details"));
    expect(screen.getByText(/deletes your existing embeddings/)).toBeVisible();
    expect(api.semanticSearch).not.toHaveBeenCalled();
    await fireEvent.click(grant);
    const input = await screen.findByLabelText("Describe the meaning or idea");
    expect(api.semanticSearch).not.toHaveBeenCalled();
    await fireEvent.input(input, { target: { value: "a lucky discovery" } });
    await fireEvent.click(screen.getByRole("button", { name: "Search cards" }));
    await waitFor(() => expect(api.semanticSearch).toHaveBeenCalledTimes(1));
    expect(api.grantGenAIConsent).toHaveBeenCalledTimes(1);
  });

  it("requires inline confirmation before withdrawing and returns to the prompt", async () => {
    render(SearchPage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    await fireEvent.click(
      await screen.findByRole("button", {
        name: /AI meaning search is allowed/,
      }),
    );
    expect(screen.getByText(/deletes your existing embeddings/)).toBeVisible();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Withdraw AI consent?" }),
      ).toHaveFocus(),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.withdrawGenAIConsent).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole("button", { name: "Keep consent" }));
    expect(api.withdrawGenAIConsent).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /AI meaning search is allowed/ }),
      ).toHaveFocus(),
    );
    await fireEvent.click(
      screen.getByRole("button", { name: /AI meaning search is allowed/ }),
    );
    await fireEvent.click(
      screen.getByRole("button", { name: "Confirm withdrawal" }),
    );
    await screen.findByRole("button", { name: "Grant consent" });
    expect(api.withdrawGenAIConsent).toHaveBeenCalledTimes(1);
    expect(api.semanticSearch).not.toHaveBeenCalled();
  });

  it("shows the consent prompt when the server rejects stale consent", async () => {
    api.semanticSearch.mockRejectedValue(
      new ApiClientError(
        "Consent required",
        "api",
        false,
        403,
        "genai_consent_required",
      ),
    );
    render(SearchPage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    await screen.findByRole("button", {
      name: /AI meaning search is allowed/,
    });
    await fireEvent.input(
      screen.getByLabelText("Describe the meaning or idea"),
      {
        target: { value: "a lucky discovery" },
      },
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search cards" }));
    await screen.findByRole("button", { name: "Grant consent" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Describe the meaning or idea"),
    ).not.toBeInTheDocument();
  });
  it("checks consent again when the signed-in account changes", async () => {
    render(SearchPage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    await screen.findByRole("button", { name: /AI meaning search is allowed/ });
    api.getGenAIConsent.mockResolvedValue({ genai_consent_at: null });
    authSession.set({ kind: "authenticated", profile: { sub: "owner-b" } });
    await screen.findByRole("button", { name: "Grant consent" });
    expect(api.semanticSearch).not.toHaveBeenCalled();
  });
  it("shows a polite initial consent check without the form", async () => {
    api.getGenAIConsent.mockReturnValue(new Promise(() => {}));
    render(SearchPage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    expect(screen.getByText("Checking AI consent…")).toBeVisible();
    expect(
      screen.getByText(
        "Your card text and search queries are sent to Google Vertex AI for semantic search. You can withdraw consent here at any time.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Describe the meaning or idea"),
    ).not.toBeInTheDocument();
    expect(api.semanticSearch).not.toHaveBeenCalled();
  });

  it("keeps the full provider description visible when the initial consent check fails", async () => {
    api.getGenAIConsent.mockRejectedValueOnce(new Error("offline"));
    render(SearchPage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    await screen.findByRole("button", { name: "Retry consent check" });
    expect(
      screen.getByRole("heading", { name: "AI consent unavailable" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "Your card text and search queries are sent to Google Vertex AI for semantic search. You can withdraw consent here at any time.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("alert")).toBeVisible();
    expect(
      screen.queryByLabelText("Describe the meaning or idea"),
    ).not.toBeInTheDocument();
    expect(api.semanticSearch).not.toHaveBeenCalled();
  });

  it("offers Retry grant beside the focused alert without showing the form", async () => {
    api.getGenAIConsent.mockResolvedValue({ genai_consent_at: null });
    api.grantGenAIConsent.mockRejectedValueOnce(new Error("offline"));
    render(SearchPage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    await fireEvent.click(
      await screen.findByRole("button", { name: "Grant consent" }),
    );
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(
      screen.queryByLabelText("Describe the meaning or idea"),
    ).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Retry grant" }));
    await screen.findByLabelText("Describe the meaning or idea");
    expect(api.semanticSearch).not.toHaveBeenCalled();
  });

  it("keeps results on failed withdrawal and clears them only after successful retry", async () => {
    api.semanticSearch.mockResolvedValue({
      items: [
        {
          id: japaneseCard.id,
          term: "resilient",
          meaning: "able to recover",
          pronunciation: null,
          score: 0.9,
        },
      ],
      index_status: "complete",
      eligible_count: 1,
      indexed_count: 1,
    });
    api.withdrawGenAIConsent.mockRejectedValueOnce(new Error("offline"));
    render(SearchPage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Meaning & concepts" }),
    );
    const manage = await screen.findByRole("button", {
      name: /AI meaning search is allowed/,
    });
    expect(manage).toHaveTextContent("AI on · Manage");
    expect(manage.closest(".heading-row")).toContainElement(
      screen.getByRole("heading", { name: "Find a card" }),
    );
    await fireEvent.input(
      screen.getByLabelText("Describe the meaning or idea"),
      { target: { value: "recover" } },
    );
    await fireEvent.click(screen.getByRole("button", { name: "Search cards" }));
    await screen.findByRole("link", { name: /resilient/ });
    await fireEvent.click(manage);
    await fireEvent.click(
      screen.getByRole("button", { name: "Confirm withdrawal" }),
    );
    await screen.findByRole("alert");
    expect(screen.getByRole("link", { name: /resilient/ })).toBeVisible();
    await fireEvent.click(
      screen.getByRole("button", { name: "Retry withdrawal" }),
    );
    await screen.findByRole("button", { name: "Grant consent" });
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Allow AI meaning search?" }),
      ).toHaveFocus(),
    );
    expect(
      screen.queryByRole("link", { name: /resilient/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Describe the meaning or idea"),
    ).not.toBeInTheDocument();
  });
});
