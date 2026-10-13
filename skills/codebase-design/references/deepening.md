# Deepening with dependencies

Read only when choosing how dependencies and tests fit behind an interface.

- **In-process:** test computation/state directly through the module interface.
- **Local-substitutable:** use the repository's existing local stand-in when its
  semantics are sufficient; explicitly cover differences from production.
- **Remote but owned:** put scenario logic behind a stable interface; inject the
  existing transport adapter and a justified test stand-in.
- **Third-party:** isolate provider behavior behind the appropriate existing
  contract; exercise failure modes with realistic fixtures and provider checks
  where available. Mocks alone do not prove a provider contract.

Keep internal substitution seams private unless callers need them. Preserve
repository-mandated ports/ACLs even with one production adapter. Prefer returning
observable results and explicit dependencies where this matches the project;
do not redesign side effects solely to make a function pure.

Replace tests only after mapping every important scenario to the new surface.
Retain valuable integration/contract coverage and regression cases. A deep
interface is not a reason to turn all tests into mocks or discard behavior checks.
