# Design alternatives

Read only when the user explicitly requests materially different interface
options for a significant architecture choice. Do not trigger a parallel design
exercise for routine tasks.

Frame scenario, constraints, actual callers, dependencies, and acceptance checks.
Compare two distinct options directly by default: smallest complete interface,
and interface optimized for the main caller. Consider flexibility only when
another real caller requires it.

If the host/user explicitly authorizes parallel design work, supply bounded
read-only briefs under its role and concurrency policy. Never invent new roles,
models, writers, or an exception to the host's scout limit. No helper edits code
or selects the final architecture.

For each option show the interface (including errors/invariants), usage example,
hidden behavior, adapters, tests, and trade-offs. The controller recommends one
option based on leverage, locality, compatibility, and seam placement. Keep the
decision in the existing plan; do not create a second lifecycle.
