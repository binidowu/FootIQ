import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import type { QueryResponse } from "../types/contract";

function buildResponse(overrides: Partial<QueryResponse>): QueryResponse {
  return {
    schema_version: "1.1",
    trace_id: "ftiq_test_trace",
    status: "ok",
    session: { session_id: "sess_test" },
    output: {
      answer: "Default answer",
      artifacts: [],
      sources: [],
    },
    metadata: {
      data_depth: "L1",
      reasoning_mode: "DATA_ONLY",
      tools_invoked: [{ tool: "search_player", duration_ms: 12, cache_hit: true }],
      usage: { total_duration_ms: 42, rate_limit_remaining: 500 },
    },
    warnings: [],
    suggestions: [],
    error: null,
    ...overrides,
  };
}

function mockFetchByQuery(queryMap: Record<string, QueryResponse>) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    const rawBody = String(init?.body ?? "{}");
    const parsed = JSON.parse(rawBody) as { query?: string };
    const key = parsed.query ?? "";
    const payload = queryMap[key];
    if (!payload) {
      throw new Error(`No mocked response for query: ${key}`);
    }
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function sendQuery(text: string) {
  const user = userEvent.setup();
  const input = screen.getByPlaceholderText(/ask about any football player/i);
  await user.type(input, text);
  await user.keyboard("{Enter}");
}

describe("UI integration matrix", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders status ok surface response with replay warnings", async () => {
    mockFetchByQuery({
      "How is Haaland doing?": buildResponse({
        trace_id: "ftiq_surface_1",
        output: {
          answer: "Haaland has 5 goals in his last 5 games.",
          artifacts: [],
          sources: [],
        },
        warnings: [
          {
            code: "DATA_MODE_REPLAY",
            message: "DATA_MODE=replay active. Using static fixtures.",
          },
        ],
        suggestions: ["Compare to Foden"],
      }),
    });

    render(<App />);
    await sendQuery("How is Haaland doing?");

    expect(await screen.findByText(/5 goals in his last 5 games/i)).toBeInTheDocument();
    expect(screen.getByText("DATA_MODE_REPLAY")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /compare to foden/i })).toBeInTheDocument();
  });

  it("renders status ok deep response with artifact image", async () => {
    mockFetchByQuery({
      "Analyze Haaland xG trend": buildResponse({
        trace_id: "ftiq_deep_1",
        metadata: {
          data_depth: "L2",
          reasoning_mode: "SYNTHESIS",
          tools_invoked: [{ tool: "show_form_chart", duration_ms: 66, cache_hit: false }],
          usage: { total_duration_ms: 201, rate_limit_remaining: 400 },
        },
        output: {
          answer: "Deep analysis complete.",
          artifacts: [
            {
              type: "plot",
              url: "/static/plots/ftiq_deep_1_form-goals.png",
              label: "Rolling Form",
            },
          ],
          sources: [],
        },
      }),
    });

    render(<App />);
    await sendQuery("Analyze Haaland xG trend");

    expect(await screen.findByText(/deep analysis complete/i)).toBeInTheDocument();
    const img = screen.getByRole("img", { name: /rolling form/i });
    expect(img).toHaveAttribute("src", "/static/plots/ftiq_deep_1_form-goals.png");
  });

  it("renders INSUFFICIENT_CONTEXT error", async () => {
    mockFetchByQuery({
      "How is he doing?": buildResponse({
        status: "error",
        output: { answer: "Please specify the player.", artifacts: [], sources: [] },
        error: { code: "INSUFFICIENT_CONTEXT", message: "Please specify the player." },
      }),
    });

    render(<App />);
    await sendQuery("How is he doing?");

    expect(await screen.findByText("INSUFFICIENT_CONTEXT")).toBeInTheDocument();
    expect(screen.getAllByText(/please specify the player/i).length).toBeGreaterThan(0);
  });

  it("renders PLAYER_NOT_FOUND error", async () => {
    mockFetchByQuery({
      "How is qmissing doing?": buildResponse({
        status: "error",
        output: { answer: "No player found matching qmissing.", artifacts: [], sources: [] },
        error: {
          code: "PLAYER_NOT_FOUND",
          message: "No player found matching qmissing.",
        },
      }),
    });

    render(<App />);
    await sendQuery("How is qmissing doing?");

    expect(await screen.findByText("PLAYER_NOT_FOUND")).toBeInTheDocument();
    expect(screen.getAllByText(/no player found matching qmissing/i).length).toBeGreaterThan(0);
  });

  it("renders AMBIGUOUS_ENTITY options", async () => {
    mockFetchByQuery({
      "How is qmulti doing?": buildResponse({
        status: "error",
        output: { answer: "Multiple matches found.", artifacts: [], sources: [] },
        error: {
          code: "AMBIGUOUS_ENTITY",
          message: "Multiple matches found.",
          options: [
            { label: "Alpha Striker (Test FC)", athlete_id: "771001" },
            { label: "Beta Winger (Mock United)", athlete_id: "771002" },
          ],
        },
      }),
    });

    render(<App />);
    await sendQuery("How is qmulti doing?");

    expect(await screen.findByText("AMBIGUOUS_ENTITY")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /alpha striker/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /beta winger/i })).toBeInTheDocument();
  });

  it("renders UPSTREAM_DOWN error", async () => {
    mockFetchByQuery({
      "How is Saka doing?": buildResponse({
        status: "error",
        output: { answer: "Provider unavailable.", artifacts: [], sources: [] },
        error: {
          code: "UPSTREAM_DOWN",
          message: "Provider unavailable.",
        },
      }),
    });

    render(<App />);
    await sendQuery("How is Saka doing?");

    expect(await screen.findByText("UPSTREAM_DOWN")).toBeInTheDocument();
    expect(screen.getAllByText(/provider unavailable/i).length).toBeGreaterThan(0);
  });

  it("supports suggestions quick-send flow", async () => {
    const fetchMock = mockFetchByQuery({
      "How is Haaland doing?": buildResponse({
        trace_id: "ftiq_suggest_1",
        output: { answer: "Haaland summary.", artifacts: [], sources: [] },
        suggestions: ["Compare Haaland and Foden"],
      }),
      "Compare Haaland and Foden": buildResponse({
        trace_id: "ftiq_suggest_2",
        output: { answer: "Comparison complete.", artifacts: [], sources: [] },
      }),
    });

    render(<App />);
    await sendQuery("How is Haaland doing?");

    const user = userEvent.setup();
    const suggestion = await screen.findByRole("button", {
      name: /compare haaland and foden/i,
    });
    await user.click(suggestion);

    expect(await screen.findByText(/comparison complete/i)).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
