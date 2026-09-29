# As-built rules

The engine follows the rules below. The worked
sequences below pin down timing for rules implemented with echoes and timed
pads in the recording phase; they are documentation examples here, not claims
that those mechanics are already implemented.

## Turn resolution

Each accepted action advances one turn in this order:

1. Remove an expired echo, then refresh pad states and linked devices.
2. Apply a valid power change, then refresh linked devices.
3. Move the player and echo using the current gate state.
4. Update pad occupancy and timers, then refresh linked devices.
5. Check player safety and the exit.

Rejected actions leave the complete state and turn counter unchanged. Safety is
checked only after the turn resolves. The hub is always safe. An elevator exit
succeeds only when the player stands on the elevator while its circuit is
powered and its linked pad is active.

## Timed-pad countdown

For a pad with timer length 3, occupying it during step 4 sets its timer to 3.
After leaving, the next three step-4 updates change the timer 3 → 2 → 1 → 0;
the pad is active before each of those updates while its timer is above zero.
At zero it is inactive unless a body occupies it. Occupying the pad again at
any point resets the timer to 3. Passive pads have timer length 0 and are active
only while occupied.

## Blocked echo command

Suppose an echo at (2, 1) has a recorded move east, but the gate at (3, 1) is
closed when that command executes. The command is consumed, the echo remains at
(2, 1), and the attempt continues. It does not retry the move on a later turn
and does not fail the attempt.

## Final-tile hold

With N recorded commands, command N moves the echo to its final tile during
turn N. The echo remains there through turn N+1, so its pad can still be active
for that turn's movement and end-of-turn checks. At step 1 of turn N+2 the echo
is removed; pad occupancy is refreshed before movement, so a passive pad held
only by the echo becomes inactive and any linked gate closes before that turn's
movement.

## Linked-device refresh timing

Assume a powered circuit and an open gate whose passive pad is occupied only
by the echo. At the start of the expiry turn, step 1 removes the echo and
refreshes the pad; the gate closes immediately. A player attempting to cross
that gate in step 3 of the same turn is blocked. Similarly, if a power change
turns the circuit off in step 2, the gate closes before movement; step 4 then
refreshes occupancy and device state again for the next turn. A pad newly
occupied during step 3 activates its linked gate in step 4, making it available
for movement on the following turn.
