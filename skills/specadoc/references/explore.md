# Explore mode

Load this reference only for `specadoc explore` or when automatic routing selects
exploration. Explore produces conversation evidence, not repository artifacts.

1. Read mandatory repository rules.
2. Before dispatching the scout, search `docs/agent/specs/` for the current
   capability of the request. Derive up to five distinctive domain terms from
   the request; use filenames, headings, and `C<n>` requirements to find
   candidates. Read at most three files with a clear semantic match. Do not
   search or read `docs/agent/archive/`: archive records are immutable history,
   not exploration context.

   If no file clearly matches, record `Relevant capability-specs: none found.`
   and continue. Otherwise record each selected path and one sentence on how it
   affects the investigation. Capability specifications describe intended
   behavior; where they conflict with the current code, code is authoritative
   and the drift must be reported.
3. Attempt exactly one bounded read-only `scout` with one concrete question.
   Pass the selected capability-spec paths and the conflict rule in its prompt.
   Continue independent controller work while it runs.
4. If the role cannot start, record the exact runtime error and continue with a
   bounded controller investigation. Do not report the primary MCP as the cause
   unless it itself failed.
5. Use a symbol-aware tool (an IDE or language-server MCP, when the runtime
   exposes one; a host may name it in `.agents/mcp-profile.json`) only for a
   concrete symbol-aware question. If absent after available tool discovery,
   state that limitation and use `rg`. If an exposed call errors, quote the
   exact call and error before falling back. State that DI bindings and dynamic
   dispatch may be incomplete.
6. Use a code-graph tool, when available, only for unfamiliar entrypoints or
   public blast radius. Keep detail minimal and depth 1; update a stale graph
   once and then stop.
7. Stress-test with a grilling skill (see `interoperability.md` → Optional
   companion skills) only when, after facts are stable, at least one
   holds: more than one material open question remains; the change touches a
   public contract, schema, security, concurrency, or money surface; or
   reconnaissance surfaced conflicting evidence. Skip it when the request is
   narrow, low-risk, and already converged with no open questions, recording
   `Grilling: skipped — <reason>` in the decision log. Without a grilling
   skill, ask the same questions directly in the decision log. Do not let
   grilling restart repository exploration or create artifacts.
8. Return the decision log, safe defaults, and at most three material questions.
   Include the selected capability-specs (or the no-match result), their effect
   on the conclusion, and every observed code/spec drift.

Read `recon-and-clarify.md` for evidence and question limits.
