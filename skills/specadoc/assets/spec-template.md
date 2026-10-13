# Specification: __CHANGE_TITLE__

**Status:** Draft  
**Risk:** __RISK__  
**Created:** __DATE__

## Goal

<Observable user or system outcome.>

## Non-goals

- <Explicitly excluded behavior.>

## Current context

<Only the current behavior and constraints needed to understand the change.>

## Affected capabilities

One entry per capability file, followed by the operations this change performs on
its `C<n>` requirements. The operations are what gets applied at archive time, so
write them as edits, not as prose.

- `docs/specadoc/specs/<capability>.md`
  - ADDED C<n> — <name of the new requirement>
  - MODIFIED C<n> — <what changes about it>
  - REMOVED C<n>
  - RENAMED C<n> — <new heading>

Use `(new capability)` after the path when this change establishes the file; then
only ADDED operations are valid.

## Requirements

### R1 — <Requirement name>

<Observable, unambiguous, testable behavior.>

## Acceptance scenarios

### A1 — <Scenario name>

**Covers:** R1

- **Given:** <initial state>
- **When:** <action or event>
- **Then:** <observable result>

## Constraints

- <Compatibility, security, platform, dependency, or performance constraint.>

## Assumptions

- <Safe default selected instead of asking a low-impact question.>

## Requirement coverage

| Requirement | Acceptance scenarios |
|---|---|
| R1 | A1 |
