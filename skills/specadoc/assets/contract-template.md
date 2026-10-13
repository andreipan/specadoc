# Contract: <name>

Owning package: `<vendor/package>` · repository of this file.
Producer service: `<service>` · Version introducing the change: `<x.y.z>`

## Goal

<Observable change to the contract, in one or two sentences.>

## Surface

| Endpoint / SDK method | Change | Breaking |
|---|---|---|
| `<METHOD /path>` / `<Class::method>` | added / changed / removed | yes / no |

State the shape of request and response only where it changed. Link the
producer's `spec.md` instead of restating behavior.

## Breaking part

<What existing callers stop being able to do, and from which version. `None` if
the change is additive.>

## Consumers

Every repository requiring this package, from the landscape map or a dependency
search. Fill the
current constraint before deciding, not after.

| Repository | Current constraint | Required version | Plan | Status |
|---|---|---|---|---|
| `<path>` | `<^x.y>` | `<^x.y>` | `<repo>/docs/agent/<slug>/plan.md` | pending / done / not needed |

A consumer more than one major behind does not receive this change by upgrading
the constraint alone. Decide here whether raising it is in scope or a separate
change, and say which.

## Verification

- Producer: <the check proving the new behavior>.
- Package: <test covering the new method or shape>, and the tag applied.
- Per consumer: the dependency lock file shows the required version, and <the check>.
