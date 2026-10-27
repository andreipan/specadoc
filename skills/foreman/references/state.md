# Minimal durable state

Use chat for a short task. For work likely to cross turns or compaction, keep one
small handoff file in a user-authorized work area. Reuse an existing task record
rather than creating a parallel task system. Do not store secrets or full logs.

Record only:

- goal, verbatim invariants, boundaries, and acceptance criterion;
- executor identifier, work area, observed binding, and continuation mechanism;
- current bounded step and state: working / waiting-user / blocked / accepted;
- last accepted artifact and exact verification evidence;
- outstanding question, user mandate, decisions, and any permission approval;
- next action, supported observation mechanism, and any live timer identifier.

Update at a transition, not after every command. State is a navigation aid, not
proof: read back referenced artifacts before accepting a result. After compaction,
reconcile the record with actual executor status before continuing. If the state
is uncertain, say so rather than fabricating progress or relaunching a writer.

Final reporting should name the delivered result, evidence, remaining limitations,
and whether an executor or timer is still active. Stop owned monitoring when
finished; never stop unrelated user processes or discard their changes.
