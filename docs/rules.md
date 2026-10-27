# As-built rules

The engine follows one fixed timing contract, described below. Recording, echo
replay, timed pads and chamber loading are implemented in the headless engine.

## Recording and retry

Enter starts a take only from the hub and records that tile as the echo start.
Enter commits from any tile, resets the player and chamber dynamics to their
starting positions, and keeps the recording and selected power configuration.
Preparation and committed movement inside the hub, and power changes at the hub
console in those phases, are free. A take captures accepted moves and waits up
to the chamber's `max_turns` limit.

Launching from the hub resets dynamic chamber state and the player to the
defined start, keeps the power configuration and recording, creates an
unadvanced echo, then captures the retry snapshot. R restores that snapshot. C
returns to the preparation state and clears power and recording. A replay
failure restores the launch snapshot; a recording failure discards that take and
returns to preparation.

## Keys, undo and the failure card

One key does one thing everywhere in play: WASD or the arrows move, Space waits,
E uses the console (or reads a nearby log terminal), Enter (or F) is the echo
key, Z or Backspace undoes, R retries from launch, C restarts the chamber, Esc
or P pauses, T opens the guide, H reveals the next hint, M mutes and F11
toggles fullscreen. Inside an overlay the arrows or WASD navigate, Space or
Enter confirm, and Esc or E close.

A gamepad reads the same action table. The D-pad moves (and walks while held),
A waits, X is the echo key, Y uses the console, B undoes, LB and RB preview
earlier and later turns, Start pauses and Back opens the guide. Inside an
overlay the D-pad navigates, A confirms, B (or Y) closes and X applies at the
console. B is "back out" wherever undo would clash with it, so in the console
and the pause menu it closes and undo keeps its key there. No pad button has two
meanings in one context. Retry, restart, hint, mute and fullscreen are key-only
(the pause menu lists retry and restart). Every key cap on the bars, in the
guide and in lesson text follows the device used last: after any pad press the
caps show the pad buttons ("A Wait"), after any key or mouse press the key names,
and an action without a pad button keeps its key cap.

The bottom bar introduces its buttons gradually. Chamber 1 shows move, wait,
undo, the power console and the echo key (nothing outside the hub can be walked
without a recording and a launch), chamber 3 adds retry and re-record, and every
later chamber shows everything. Wait, undo, restart, pause, guide, hint, mute and
fullscreen are always shown. A new button blinks for a few seconds the first
time its chamber opens (it stays lit with reduced motion). Only the bar and the
guide's Controls page hide an action; its key keeps working.

The mouse is equivalent to the keys. Clicking a tile next to the technician
moves; clicking the technician's own tile waits, or opens the console while the
technician stands on it; other tiles do nothing. Bar buttons, console rows (a
circuit row selects and toggles it, the apply row applies), failure-card
options, pause-menu items and timeline slots are clickable, and a right-click
closes the console, guide, hint and pause menu. The failure card has no close:
it always needs a choice. Every click goes through the same path as its key, so
disabled actions show their reason and undo and the playtest counters match.

The echo key follows the phase: *Record* in the hub before a take, *Save
recording* while recording, *Launch echo* in the hub once a take is saved,
*Return to hub to launch* (disabled) when a saved take is outside the hub, and
*Echo running* (disabled) during replay. Q is still accepted as a hidden alias
of launching so old habits do not fail silently; it never records or saves.
Chamber select is an item in the pause menu (key L there); it is not a play key.
Re-record discards the current take, keeps the selected power and returns to
preparation. It is a bar button and a pause-menu action without a bare key.

The pause menu lists Resume, Undo, Retry from launch, Restart chamber,
Re-record, Chamber select, Settings, Controls and Quit to title. Settings holds
music volume and SFX volume (0 to 7, applied at once), mute, reduced motion, the
CRT look and fullscreen; Left and Right (or a click on the left or right half of
a row) change a value, and every change is saved at once. Controls opens the
guide on its Controls page. The CRT look is Pyxel's retro screen mode (the window
adds the scanline filter); it is off by default, so the crisp mode is used. The
window icon is cut from the player sprite and silently left at the default if
that fails.

Safe and dark floor differ by texture as well as colour: lit and hub floor are
striped or speckled while the dark remap flattens the floor towards a single
grey. A test converts both to grayscale and compares where the grey level steps
sharply, so a brightness match cannot hide the difference.

Moves are eased on screen: a step is a steady glide of about a quarter of a
second (the game runs at 60 frames per second), a refused move leans toward the
wall and back, and gates, pads, elevators, the echo, lighting changes, failures
and clearing a chamber have short animations. The rules step at once on every
input and a new input ends any running animation first, so nothing is queued or
lost. With reduced motion on there are no glides, shakes, fades or flashes: each
change simply shows its end state.

Holding a movement key walks continuously: a fresh press steps at once, and while
the key stays down the next step starts the frame the previous glide lands, so
the walk speed is one tile per 15 frames (also with reduced motion, which only
skips drawing the glide). A held key stops when the recording is full, after a
step that went nowhere (a wall or closed gate: it is explained once, never
again while the key is held), when the attempt fails, or on release; pressing
again steps at once. Mouse clicks are single steps. Undo plays the undone step
backwards at double speed (instantly with reduced motion), and a new input still
ends it first. Small idle touches (a breathing bob, the echo's fading trail, a
console flicker, a pulse along the powered conduit rails, a few dust motes over
lit floor, timeline slots that pop when filled (the sprite is scaled about its centre, no
extra frame), a pulsing playback slot, an
eased power bar, and a console drawer and bar buttons that slide) are all
presentation and are off with reduced motion.

Sound is presentation only. Music plays on channels 0-2 and effects on channel
3, one effect per step: a failure, then a clear, a rejected input, a recording
or launch change, a gate, elevator, pad or power change, and last a move or
wait (a recorded step ticks instead). Menu moves and picks have their own
effects. Music follows the screen: the title theme on the menus, calm music
while preparing and recording, a replay variant while the echo runs, a short
sting on a clear and the final theme after the last chamber. A missing track
is simply silent, and the game runs without an audio device.

The guide (T) has seven pages: Goal, Controls, Objects, Echo, Power, Hints and
Precise rules. The arrows or WASD, or the previous and next rows, change page;
Esc, E or a right-click closes it. Controls is generated from the same action
table as the bars and shows only the actions the chamber has introduced. H
reveals the next hint and opens the guide on the Hints page, which lists the
revealed hints and how many remain; each reveal is counted once.

Every action that cannot run right now is disabled with a reason. Pressing it
anyway shows that reason in place and never fails silently.

Undo restores an earlier stored game state; it never runs the rules again. Every
accepted input pushes one entry: moves, waits, console opens and circuit toggles,
power changes, record, save, launch, free hub moves, R, C and re-record. Rejected
inputs and disabled keys push nothing. History holds up to 10,000 entries, then
drops the oldest. A guided lesson rewinds with the game, so undo also steps back
to the lesson's previous objective.

When a move fails the attempt, a failure card opens over the room as it was
before the failing move and nothing is restored yet. Z undoes the failing move,
R retries from launch (the default; any other key also takes it) and C restarts
the chamber. After a recording failure there is no launch to retry from, so Retry
is disabled and any key discards the take as the rules describe. A failure
counts one reset; retrying from the card does not count a second.

## Power console, previews and markers

Before a take and once it is saved, a circuit switch in the console takes effect
as soon as it is toggled and costs no turn; every accepted toggle is one undo
step. A choice over the generator's capacity is refused with its reason, nothing
changes, and it counts once as an unsafe power choice; Enter then only closes the
console. While recording and during replay the toggles are only staged: nothing
changes and no turn passes until Apply, which commits the whole choice and
costs one turn. The room shows the pending choice while the console is open:
tiles that would go dark are dimmed and hatched, and devices that would gain or
lose power pulse (a static outline when reduced motion is on).

The game can show what the next turns will do because the rules are
deterministic. Once a take is saved, hovering a timeline slot or pressing `[` and
`]` previews that turn: it runs the real turn function on a copy, assuming the
player waits where they stand (before launch, from the start tile), and ghosts
the echo and the predicted pad, gate and elevator states. During replay the
strip marks turns that already happened and only future turns can be previewed.
Previews never change the live game, and any gameplay key returns to the live
view. The strip states when the echo leaves: with N saved commands it is present
through turn N+1 and gone from turn N+2, so four saved commands read "echo leaves
after turn 5".

In the room, a timed pad shows how many turns of activity it has left, and a
gate or elevator that will stop next turn if the player waits is tagged. Tiles
next to the player that are unlit are outlined in red, with a warning mark while
moves spend turns. Standing next to a gate or elevator, or hovering it, draws a
line to its pad and two icons: the power bolt (circuit on or off) and the pad
letter (pad active or not). A machine needs both. Once a take is saved, a faint
dotted line shows the echo's recorded path, and during replay an arrow shows its
next move.

Chambers load from JSON through `engine.loader`. Grid tile names use the
`TileType` values; positions are `[x, y]`. The loader validates all links,
positions, unique IDs, circuit capacity, hub/start/console/exit requirements,
pad timer lengths and the 1–12 `max_turns` range.

All six chambers use the same rules and each is built around one idea. The first
two can be solved after launching an empty recording; chambers 3 to 6 cannot be
solved without an echo (the tests exhaust every no-echo play to prove it).

| Chamber | Idea | What the echo is for |
|---|---|---|
| 1 | movement | nothing: switch on the route and reach the lift |
| 2 | power | nothing: pick circuits that fit the generator |
| 3 | echo | standing on a passive pad while you cross its gate |
| 4 | darkness | standing on a pad in an unlit nook; the generator cannot light the nook and run the machines at once, so the take is made lit and the power is swapped before launch |
| 5 | timed pads | crossing a gate on a pad's countdown, then waiting on a passive pad while you ride the lift |
| 6 | combined | all of the above: a dark pad opens the first gate, then a countdown holds the second gate and the lift |

Every chamber is built around a hub room of 80 to 100 tiles with the start tile
as its only door, so there is space to walk about before a take. The power
console stands deeper in the room, four tiles from the door along its row, so
reaching it is a short walk that fits on screen with the door. The console is
used only while the technician stands on its tile: the E key and a click on the
tile are refused with a reason anywhere else, and a power change is free before
a take and after it is saved but, during a replay, costs one turn on top of the
walk there and back. The room is always lit and walking in it is free, and the
route begins at the door, so a take that starts anywhere else in the room is
never faster than one that starts at the door. The chambers are 15 to 19 tiles wide and 12 or 13 tall, so the camera
scrolls them on a 1280x720 window.

Each hub room also holds two or three log terminals, small story props on hub tiles
away from the console and the door. They are listed in the chamber file as
`terminals` (a hub tile and one to three short lines each); the rules, the
solver and the engine never read them, and the tile stays ordinary walkable hub
floor. The use key (E) reads a terminal when the technician stands on it or
next to it in the hub and is not standing on the console; the console keeps the
key on its own tile. Clicking the terminal tile the technician stands on, or
pressing the bar button that then reads *Read log*, does the same. On a terminal
tile a click on your own tile reads instead of waiting, so use the bar's Wait
button to wait there; clicking an adjacent terminal tile moves onto it, like the
arrow key, and clicking the console tile never opens a log. The card reveals one line at a time: Space,
Enter or a click shows the next line and then closes it, and Esc, E or a
right-click closes it at once. Reading is free at every stage of a take, passes no turn,
changes no chamber state and leaves nothing for undo. Where no terminal is
near, the key keeps its power-console reason.

Each of chambers 4 to 6 is a short route in three beats: the idea on its own (the
first gate or pad), an easy use of it (the recorded walk), and a twist that
combines it with earlier chambers (the power swap, the shared countdown). Difficulty
is measured by the fewest turns of the shortest play, which rises 2, 3, 7, 9, 11, 13
over the six chambers; `tools/solve.py --all` prints that table with the fewest
recorded commands, the lowest peak load and the idea check for each chamber.

The title screen
leads to level select by Enter, Space or clicking Start. Chamber selection uses
WASD/arrow keys and Enter or a mouse click on an unlocked card; menus do not
advance turns. Completing a chamber unlocks the next one, stored as an
`unlocked` integer in the per-user progress file, which also holds a `version`,
per-chamber `goals` and player `settings` (volumes 0-7, mute, reduced motion,
CRT). A missing or damaged field falls back to its default and never clears
valid unlocks. Validated guided steps, lesson summaries and ordered hints live
in each chamber JSON; their text names keys only through placeholders that the
action table fills in. Each visit offers a guided lesson (Enter) or free play
(F). A guided step is one instruction on the Next step line plus a highlight;
doing the action advances it, and unrelated gameplay inputs are inert. A card
appears only for a step that introduces a new idea, and closes on Enter, a click
or the action itself. Room and HUD hover explanations use the same live state.
Hint reveals are counted for the current run. Reading and hovering never advance
turns. C restarts a guided lesson; R keeps the launch-snapshot semantics and
returns guidance to the replay objective. See `docs/tutorials.md` for the lesson
flow.

The UI writes one local JSONL record per chamber visit when it completes, is
left through level select, or the game exits normally. The record has a random
attempt ID, chamber, completion status, elapsed time, resets, hints revealed,
over-budget console confirmations, and guided/free mode. It does not include player inputs or
personal identifiers. A failed turn, accepted R retry or C clear increments
the reset count; an over-budget confirmation never advances the engine. The record
also counts undos, refused (disabled) key presses by action, failure-card
choices and timeline previews.

## Camera and off-screen markers

The camera only changes what is drawn; it never touches the rules or the input.

- **Tile size.** Each window and chamber gets the largest tile that shows the
  whole framed area (the route plus a one-tile wall border) with the console
  closed, never below a floor of about seven rows in the room (80 px at
  1280x720) and never above twice the reference cell. A chamber that fits fills
  the room and never scrolls. One that would need smaller tiles keeps the floor
  size and scrolls.
- **Follow.** The view follows the player's drawn position with a dead zone
  around the middle, eases towards its target, stays inside the framed area and
  centres a chamber smaller than the view. Opening the console narrows the view
  without changing the tile size, so the camera scrolls if the player would be
  covered. Reduced motion jumps to the target at once. Opening a chamber, a
  retry, a restart or an undo that moves the player more than one tile snaps the
  view.
- **Mouse.** Clicks and hover use the view that is currently drawn, including
  while the camera moves or the room shakes. Only tiles that are visible, and not
  under the console drawer (also while it slides), can be hit.
- **Markers.** A small arrow on the room's edge points at each gate, pad,
  elevator or echo that is out of view, coloured by kind (amber gate, green pad,
  white elevator, blue echo). A guided step's target tile gets a yellow one.
  Nothing is drawn while everything is visible. A linked gate or elevator that
  is hovered or next to the player draws its link line clipped to the edge and
  ends it in an arrow when the pad is out of view.

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

## Solver, goals and taught ideas

`engine/search.py` solves a chamber with the real engine (`recording.act`,
`recording.enter`, `recording.launch` and `turn.step`), identifying states by
`State.search_key()`. `tools/solve.py <chamber>` prints the report and the
shortest trace; `tools/solve.py --all` prints the difficulty table. A search
that reaches its state or time cap is reported as inconclusive, never as a
verdict.

When the start tile is the hub's only door, the search treats the rest of the hub
as inert: it holds no pad, gate or lift, and the technician can leave it only
through the door. Walking inside it matters only as a trip between the door and a
console, so the search replaces every hub step by a trip along a shortest path
between those stops, costing its length in turns, and takes a start only at a
stop. That is exact before and between takes. It is exact during replay too: a
longer walk is the shortest path followed by waits, which cost the same, and a
power change waits for its turn at the console just as well. While recording it is
an assumption, because those steps become recorded moves and an echo that a
closed gate holds back would replay them from another tile; it was checked to give
the same optima on chambers 3 to 6. `tools/solve.py --full-hub` turns the trips
off for recording only (the take's start and replay keep them) so it can be
re-verified when chambers change; it is much slower and needs a larger state cap
(`--max-states 6000000`, about a minute per chamber). A hub with a second door is
searched in full. Because the console is a walk from the door, a power change
during replay costs the trip as well as its turn, so the fewest-turn plays set
their power before launching.

**Turns.** A run's turns are the turn-consuming actions from the chamber start
to the exit: every move, wait and console change made while recording or
replaying. Walking inside the hub before a take or launch, changing power at the
console before launch, starting a take, saving it and launching are free. The
count covers the take that was saved plus the launch that reached the exit.
Retrying from launch does not add the discarded attempt (the count returns to
its value at launch), and a take that failed is thrown away: starting a take
sets the turn counter to zero. The result card measures exactly this, so a
player run and the solver's optimum are comparable. Reaching the exit while
still recording also ends the chamber; its turns are the take's turns and its
recorded commands are the take so far.

**Report.**

- *Fewest turns*: the least total turns of any play.
- *Fewest recorded*: the shortest saved recording of any play (0 means an empty
  recording is enough), with the fewest turns among those plays.
- *Lowest peak load*: the lowest power load in force during any turn, among the
  plays that take the fewest turns.
- *Shortest solutions*: how many distinct plays take the fewest turns. A play is
  the ordered list of its turn-consuming actions, the hub tile a take starts on,
  the power set at launch and each console change; free power set before
  recording only has to make the take legal and is not part of the identity.
  The count stops at a cap and is then shown as "at least".
- *Idea skipped*: whether some play avoids the chamber's taught idea.

**Goals.** A chamber may store `goals` (`turns` and `recorded`) copied from the
solver's fewest turns and fewest recorded, and a trace for each in
`levels/solutions/chamber_NN.goals.json`. The result card shows the run's turns
and recorded commands against the targets. Goals met are saved with the
progress and are only ever upgraded; they never decide what is unlocked. The
level select shows up to three marks per card: cleared, turn goal, recording
goal. A recording goal equal to the chamber's recording limit is met by every
clear, so that chamber shows no recording mark, no recording target on its
result card and saves no recording goal.

**Taught ideas.** A chamber may name its `idea` (`movement`, `power`, `echo`,
`darkness`, `timed_pads` or `combined`). A play skips the idea when:

- `movement`: nothing is ever powered. The lift always needs a powered circuit,
  so this stays false unless a chamber is malformed.
- `power`: every circuit stays powered for the whole play. Impossible when the
  generator cannot carry them all, which is when allocation is needed.
- `echo`: the recording is empty, or the exit is reached with no echo at all
  (checked by exhausting every no-echo play, whatever its length).
- `darkness`: the echo never stands on an unlit tile.
- `timed_pads`: the chamber is still solvable with every pad timer at zero, so
  no countdown is needed.
- `combined`: any one of the ideas the chamber exercises is skipped. The echo
  is always counted, power when the circuits together exceed the generator,
  darkness when a circuit lights a zone and timed pads when a pad has a timer.

The idea checks cover every play unless a horizon (a turn limit) is given.
