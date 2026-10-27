"""Live explanations shared by keyboard help and pointer inspection."""

from echo_shift.engine import lighting
from echo_shift.engine.model import Phase, Position, State
from echo_shift.engine.turn import Move, Wait
from echo_shift.ui import controls
from echo_shift.ui.controls import key_text, stages_power
from echo_shift.ui.story import Terminal


def cap(action_id: str) -> str:
    return controls.cap(action_id)


def pad_label(state: State, pad_id: str) -> str:
    return chr(
        ord("A")
        + next(i for i, pad in enumerate(state.chamber.pads) if pad.id == pad_id)
    )


def command_name(action: object) -> str:
    if isinstance(action, Wait):
        return "Wait"
    if isinstance(action, Move):
        return {(1, 0): "Right", (-1, 0): "Left", (0, -1): "Up", (0, 1): "Down"}[
            (action.dx, action.dy)
        ]
    return "Empty"


def room_info(
    state: State,
    position: Position,
    lighting_notes: bool = True,
    terminals: tuple[Terminal, ...] = (),
) -> tuple[str, str]:
    title = state.chamber.tile_at(position).value.upper()
    parts = []
    if position == state.player:
        parts.append(
            f"Amber technician: you control this character with {key_text('move')}."
        )
    if position == state.echo_position:
        parts.append(
            "Blue echo: repeats your saved commands and may share your tile. It is immune to darkness and never supplies power."
        )
    if position in state.chamber.hub:
        parts.append(
            "The hub is permanently lit and safe. Preparation and committed movement inside it are free."
        )
    if position in state.chamber.consoles:
        title = "HUB CONSOLE"
        parts.append(
            f"{cap('console')} opens power selection. {cap('nav_prev')}/{cap('nav_next')} selects, {cap('toggle')} switches a circuit, {cap('apply')} applies, {cap('close')} closes. Changes are free before recording and after saving; during a recording or replay they wait for {cap('apply')} and cost one turn."
        )
    if any(terminal.position == position for terminal in terminals):
        title = "LOG TERMINAL"
        parts.append(
            f"Log terminal: press {cap('console')} to read it when you stand on or next to it. "
            "Reading is free and changes nothing in the chamber."
        )
    for pad in state.chamber.pads:
        if pad.position == position:
            label = pad_label(state, pad.id)
            title = f"PAD {label} / " + ("TIMED" if pad.timer_length else "PASSIVE")
            parts.append(
                f"Occupied: {'yes' if pad.id in state.pad_occupied else 'no'}. Active: {'yes' if pad.id in state.pad_active else 'no'}."
            )
            if pad.timer_length:
                parts.append(
                    f"Timer: {dict(state.pad_timers).get(pad.id, 0)}/{pad.timer_length}. Occupying it resets the timer. Each accepted turn while empty decreases it by 1. At zero it is inactive unless occupied."
                )
            else:
                parts.append(
                    "No timer. Active only while the player or echo occupies this tile."
                )
            links = [
                d.id.replace("-", " ")
                for d in state.chamber.devices
                if d.pad_id == pad.id
            ]
            parts.append(
                "Controls: "
                + ", ".join(links)
                + ". Each also needs its own powered circuit."
            )
    for device in state.chamber.devices:
        if device.position == position:
            label = pad_label(state, device.pad_id)
            running = (
                device.id in state.gates_open or device.id in state.elevators_running
            )
            title = device.kind.value.upper() + f" {label}"
            parts.append(
                f"{'Open/running' if running else 'Closed/stopped'}. Circuit {device.circuit_id.upper()}: {'ON' if device.circuit_id in state.powered_circuits else 'OFF'}. Linked pad {label}: {'active' if device.pad_id in state.pad_active else 'inactive'}."
            )
            parts.append(
                "Needs BOTH power and an active linked pad. A pad that becomes active this turn opens its gate for the next turn's movement."
            )
            if device.kind.value == "elevator":
                parts.append("Finish by standing here while the elevator is running.")
    if state.chamber.tile_at(position).value == "wall":
        parts.append(
            "A wall blocks movement. Rejected player moves spend no turn and save no recording command."
        )
    elif lighting_notes and position not in state.chamber.hub:
        zone_ids = {zone.id for zone in state.chamber.zones if position in zone.tiles}
        light_circuits = [
            c.id.upper().replace("-", " ")
            for c in state.chamber.circuits
            if zone_ids.intersection(c.zones)
        ]
        if zone_ids:
            parts.append(
                "Zones: "
                + ", ".join(sorted(zone_ids)).upper()
                + ". Lighting circuits: "
                + (", ".join(light_circuits) or "none")
                + ". A zone groups tiles lit by the same circuit."
            )
        parts.append(
            "Lit: safe to end a turn here."
            if lighting.is_safe(state, position)
            else "Dark: ending a turn here fails your attempt. The echo is safe in darkness."
        )
    return title, " ".join(parts)


def topics(
    state: State,
    pending: frozenset[str],
    console: bool = False,
    terminals: tuple[Terminal, ...] = (),
) -> list[tuple[str, str, str]]:
    load = sum(c.load for c in state.chamber.circuits if c.id in state.powered_circuits)
    pending_load = sum(c.load for c in state.chamber.circuits if c.id in pending)
    echo_next = (
        command_name(state.recording[state.echo_index])
        if state.echo_index < len(state.recording)
        else (
            "Holding final tile"
            if state.echo_position is not None
            else "No active echo"
        )
    )
    result = [
        (
            "power",
            "POWER CAPACITY",
            f"Applied load: {load}/{state.chamber.capacity} units. "
            + (
                f"Pending choice: {pending_load}/{state.chamber.capacity}. "
                if console
                else ""
            )
            + "Capacity limits simultaneous powered circuits; it does not drain. Over-budget requests are refused entirely and spend no turn. An active pad does not supply electricity.",
        ),
        (
            "safety",
            "LIGHT AND SAFETY",
            f"Your tile is {'safe' if lighting.is_safe(state, state.player) else 'dark'}. The hub is always lit. Elsewhere, a tile is lit when a circuit powering its zone is ON. Ending a turn on an unlit tile fails. Power changes affect safety on that same turn.",
        ),
        (
            "state",
            "CURRENT PLAY STATE",
            f"State: {state.phase.value.upper()}. Accepted turns: {state.turns}. Prepare: choose power at the hub. Recording: capture moves/waits. Committed: saved take, ready to launch. Replay: you and the echo act together. Result: elevator reached.",
        ),
        (
            "recording",
            "RECORDING AND LAUNCH",
            f"Saved commands: {len(state.recording)}/{state.chamber.max_turns}. {cap('echo')} starts a take only at the hub; {cap('echo')} again saves it from anywhere. Only accepted moves/waits are saved. A full take refuses further actions until saved. {cap('echo')} at the hub then launches: it resets dynamics and player position, keeps power and the take, and creates an unadvanced echo.",
        ),
        (
            "echo",
            "YOUR BLUE ECHO",
            f"Next command: {echo_next}. One echo repeats one saved command per accepted replay turn. It may overlap you, presses pads and ignores darkness. Closed gates and walls block it; that command is consumed. After its last command it stays on its final tile for one more turn, then leaves.",
        ),
        (
            "turns",
            "MOVEMENT, WAITING AND TIMING",
            f"{key_text('move')} move one tile; {cap('wait')} waits without moving. Accepted moves, waits and active-take console changes spend a turn. Rejected player moves spend nothing. Echo expiry happens first, then power changes, movement, pad/device updates, and safety/exit checks. Reading, hovering, menus and pause never advance turns.",
        ),
        (
            "recovery",
            "RETRY, CLEAR AND CONTROLS",
            f"{cap('undo')} undoes the last accepted input. {cap('retry')} restores the launch snapshot: same take and launch power, starting player position, unadvanced echo and reset pads. {cap('restart')} clears the entire chamber, including power and recording. A failure shows a card: undo, retry (replay failures) or restart; a recording failure discards the take. {cap('pause')} pauses (chamber select is in the pause menu), {cap('hint')} reveals a counted hint, {cap('fullscreen')} toggles fullscreen. {cap('guide')} opens or closes the guide.",
        ),
    ]
    circuit_rule = (
        f"During a recording or replay a change waits for {cap('apply')} and costs one turn."
        if stages_power(state)
        else "Here a switch takes effect at once and costs no turn."
    )
    for circuit in state.chamber.circuits:
        result.append(
            (
                "circuit:" + circuit.id,
                circuit.id.upper().replace("-", " "),
                f"Cost: {circuit.load} units. Applied: {'ON' if circuit.id in state.powered_circuits else 'OFF'}. Pending: {'ON' if circuit.id in pending else 'OFF'}. Lights zones: {', '.join(circuit.zones) or 'none'}. Powers devices: {', '.join(circuit.devices) or 'none'}. {circuit_rule}",
            )
        )
    positions = sorted(
        Position(x, y)
        for y, row in enumerate(state.chamber.tiles)
        for x, tile in enumerate(row)
        if tile.value != "wall"
    )
    for position in positions:
        title, detail = room_info(state, position, terminals=terminals)
        result.append((f"tile:{position.x},{position.y}", title, detail))
    for index in range(state.chamber.max_turns):
        action = state.recording[index] if index < len(state.recording) else None
        current = (
            state.phase is Phase.REPLAY
            and state.echo_index == index
            and action is not None
        )
        result.append(
            (
                f"timeline:{index}",
                f"TIMELINE SLOT {index + 1}",
                f"Command: {command_name(action)}. "
                + (
                    "Blue outline: the next command the echo will execute. "
                    if current
                    else ""
                )
                + "Each slot holds one accepted move or wait. Empty slots contain no command. During replay the next command executes only when an action spends a turn."
                + (
                    f" Hover a slot, or press {cap('preview_prev')} / {cap('preview_next')}, to preview that turn."
                    if state.phase in (Phase.COMMITTED, Phase.REPLAY)
                    else ""
                ),
            )
        )
    return result
