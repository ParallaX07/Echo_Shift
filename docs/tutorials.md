# Guided lessons and contextual help

Every chamber visit starts with a choice. **Enter starts the guided lesson**;
**F starts free play**. Previously unlocked chambers offer both choices again.
Reading or selecting a mode never advances the engine. Existing progress saves
continue to contain only the highest `unlocked` chamber.

A guided step first explains the mechanic, its purpose and the next action.
Press Enter (or click the dialogue footer) to acknowledge it, release the key,
then perform the action separately. The objective stays visible at the top of
the room or inside the power console. Yellow outlines highlight a target tile,
timeline slot or status field; a yellow `*` marks a target circuit. A wrong
gameplay action is refused without changing power, positions, timers, recording
or turns. Console selection remains available. A step advances only after its
expected action and actual outcomes match, never merely from pressing a key.

Chamber 1 teaches the technician, hub, lighting, console, empty-take launch,
movement, timed pads, retry and elevator completion. It includes a required
retry from the launch snapshot. Chamber 2 deliberately tries applying all three
circuits (70/60), observes rejection, removes auxiliary power, applies 55/60 and
uses the timed pad's active window. Chamber 3 records Right and three separate
Waits, then uses the echo to hold a passive pad while crossing the gate. The
layouts, power costs, recording limits and solution traces are unchanged.

**T opens contextual help**, with arrows selecting previous/next topics and
T, Esc or Enter returning to the previous dialogue or objective. Help is also
available from an open console. **H reveals a counted hint**; returning preserves
the objective, including when help was opened inside a hint. **P pauses** and
resumes the same step. **C clears power and recording and restarts a guided
lesson**. **R after launch restores the engine's launch snapshot**; during a
lesson it returns guidance to the first replay action, except for the required
retry exercise, which advances to its next action. R before launch has no effect.
**L returns to chamber selection**. F11 and Alt+Enter remain fullscreen shortcuts.

Hover room objects, circuit rows, the power meter, safety state, chamber heading
or timeline slots for live explanations. Timed pads show occupied and active
flags and remaining countdown separately. Devices show their circuit and linked
pad requirements. Timeline slots identify commands and the next replay command.
The keyboard help contains the same object and HUD explanations, alongside
recording, darkness, echo lifetime, waiting, blocked commands and recovery rules.
Hovering never performs an action or advances the lesson.

## Content and verification

Chamber JSON has optional `tutorial_steps` and `lesson_summary` fields. Each step
has a unique `id`, `title`, `explanation`, `objective`, `action`, `expected`
outcomes, and a `target` highlight. UI loading validates required fields,
supported actions/outcomes, coordinates, circuit/pad/gate references and timeline
indices. Fixtures without `tutorial_steps` still work. The tutorial controller
and explanation functions do not import Pyxel; they observe the real engine.
There is no alternative tutorial simulation or modification of timing rules.

Local visit telemetry includes `mode` (`guided` or `free`) so moderator findings
can distinguish the experiences. The deliberately rejected request is counted
as an over-budget confirmation.

Run the automated checks with `uv run pytest -q`.
