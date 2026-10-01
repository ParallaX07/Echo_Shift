# As-built rules

The engine follows the rules below. Recording, echo replay, timed
pads and chamber loading are implemented in the headless engine.

## Recording and retry

Enter starts a take only from the hub and records that tile as the echo start.
Enter commits from any tile, resets the player and chamber dynamics to their
starting positions, and keeps the recording and selected power configuration.
Preparation and committed movement inside the hub, and power changes at the hub
console in those phases, are free. A take captures accepted moves and waits up
to the chamber's `max_turns` limit.

Q from the hub resets dynamic chamber state and the player to the defined start,
keeps the power configuration and recording, creates an unadvanced echo, then
captures the retry snapshot. R restores that snapshot. C returns to the
preparation state and clears power and recording. A replay failure restores the
launch snapshot; a recording failure discards that take and returns to
preparation.

Chambers load from JSON through `engine.loader`. Grid tile names use the
`TileType` values; positions are `[x, y]`. The loader validates all links,
positions, unique IDs, circuit capacity, hub/start/console/exit requirements,
pad timer lengths and the 1–12 `max_turns` range.

Chambers 1–3 use the same rules. The first two can be solved after launching an
empty recording; the third needs an echo on a passive pad. The title screen
leads to level select by Enter, Space or clicking Start. Chamber selection uses
WASD/arrow keys and Enter or a mouse click on an unlocked card; menus do not
advance turns. Completing a chamber unlocks the next one, stored as an
`unlocked` integer in the per-user progress file. Validated guided steps, lesson summaries and ordered hints live in each chamber
JSON. Each visit offers a guided lesson (Enter) or free play (F). Guided steps
explain a mechanic, then check the player's action and resulting state before
advancing; unrelated gameplay inputs are inert. T opens keyboard-selectable
contextual help; room and HUD hover explanations use the same live state. Hint
reveals are counted for the current run. Reading and hovering never advance
turns. C restarts a guided lesson; R keeps the launch-snapshot semantics and
returns guidance to the replay objective. See `docs/tutorials.md` for controls.

The UI writes one local JSONL record per chamber visit when it completes, is
left through level select, or the game exits normally. The record has a random
attempt ID, chamber, completion status, elapsed time, resets, hints revealed,
over-budget console confirmations, and guided/free mode. It does not include player inputs or
personal identifiers. A failed turn, accepted R retry or C clear increments
the reset count; an over-budget confirmation never advances the engine.

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
any point resets its configured timer length. JSON pads default to timer length
3; passive pads use timer length 0 and are active only while occupied.

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
