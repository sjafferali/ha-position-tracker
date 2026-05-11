# Position Tracker

A Home Assistant custom integration that adds **synthetic angle tracking
in degrees** to `cover` entities that don't have native position feedback.
Exposes the angle as a `number` entity (slider) — same UX as Eight Sleep
base controls.

## What it's for

Some cover entities (adjustable beds, RF blinds, time-controlled garage
doors, etc.) accept open / close / stop commands but never tell you *where*
the motor is. This integration wraps such a cover with a new `number`
entity that:

- Counts every `cover.open_cover` / `cover.close_cover` call against the source
- Multiplies by a calibrated per-press delta in degrees
  (`max_angle / presses_to_full_travel`)
- Exposes the result as a 0 – max° slider you can both read and drag
- Forwards drag-to-set into the right number of source presses

## How it counts presses

Listens to `EVENT_CALL_SERVICE` for `cover.open_cover` / `cover.close_cover`
calls targeting the source entity. Each call = one press.

It does **not** rely on source-cover state transitions for counting, because
back-to-back presses can leave the source's state at `opening` continuously,
and HA suppresses duplicate state events. Source state *is* used to update
the `move_direction` and `is_moving` attributes.

## Limitations

- **No ground truth.** If the source cover is moved by another path the
  integration can't observe (e.g., a physical remote on the bed), angle
  drifts. Use the `position_tracker.set_position` service to re-sync.
- **End-stop overrun.** Pressing past the mechanical limit still counts as a
  press, so estimates exceed reality at the extremes. Clamped to `[0, max]`,
  but the over-count silently inflates `presses_since_sync`. Snap-to-zero on
  a Flat preset (via your own automation calling
  `position_tracker.set_position`) is recommended.
- **Per-press variance.** Real motors don't move identical distances under
  different loads. Drift accumulates over many presses. Re-sync periodically.
- **Source pulse-count changes break calibration.** If the source integration
  changes how many actual motor pulses each `open_cover` call produces, the
  per-press delta is wrong. Re-calibrate.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. URL: `https://github.com/sjafferali/ha-position-tracker`, category:
   *Integration*
3. Install **Position Tracker**, restart Home Assistant.

### Manual

Copy `custom_components/position_tracker/` into your HA config's
`custom_components/` directory. Restart.

## Setup

1. **Settings → Devices & services → Add Integration → Position Tracker**
2. Name the device (e.g., "Theater Bed Angles")
3. For each motor you want to track:
   - **Display name**, e.g., `Back Angle`
   - **Source cover** entity
   - **Maximum angle (degrees)** — the motor's mechanical full-travel range
     (typical bed values: 65° for back, 45° for legs)
   - **Presses to full travel** — calibration; how many `open_cover` calls
     get the source from 0° to max°
   - **Initial angle (degrees)** — default 0
4. Click "Add another angle" or "Finish"

You'll get one `number` entity per tracked motor, e.g.:
- `number.theater_bed_angles_back_angle`
- `number.theater_bed_angles_legs_angle`

### Calibrating "presses to full travel"

1. Move the source cover to fully closed (0°).
2. Tap **Up** on the source until fully open. Count your taps.
3. Use that number for "presses to full travel".

You can re-edit calibration any time via Settings → Devices & services →
Position Tracker → Configure.

### Tip: lower the source's pulse count for fine slider control

Many bed integrations (e.g., `ha-adjustable-bed` for OKIN CB24) default to
3 motor pulses per `open_cover` call (~900 ms of motion). With a 65° back
travel and 30 presses, that's ~2°/press — and 2° is the minimum step you
can land on.

For finer slider control, lower the source integration's `motor_pulse_count`
to 1. Each press becomes ~300 ms of motion (~0.7° on the same bed), giving
~3× finer slider precision. Total motion time per slider drag stays the
same — you just send more, smaller commands. **Re-calibrate** the
`presses_to_full_travel` value after changing pulse count.

The trade-off: tapping the *source* cover's up/down (not the wrapper slider)
will produce more visible stop-start gaps with a smaller pulse count.

## Service

### `position_tracker.set_position`

Manually snap a tracked angle to a known value (in degrees).

```yaml
service: position_tracker.set_position
data:
  entity_id: number.theater_bed_angles_back_angle
  position: 0   # bed is currently flat
```

Recommended: wire this to your bed's Flat preset so the angle auto-snaps to
0° when you go flat.

## Status attributes

Every tracked number exposes:

| Attribute                    | Meaning                                       |
| ---------------------------- | --------------------------------------------- |
| `source_entity`              | The wrapped cover entity ID                  |
| `max_angle`                  | The configured maximum angle (degrees)       |
| `presses_to_full`            | Calibration value                            |
| `delta_per_press_degrees`    | `max_angle / presses_to_full`                |
| `presses_since_sync`         | Press count since last manual sync (drift)   |
| `is_moving`                  | True while source state is opening/closing   |
| `move_direction`             | "open", "close", or null                     |
| `last_sync_at`               | ISO timestamp of last `set_position` call    |
| `seconds_since_sync`         | Convenience derived value                    |

## Slider re-targeting mid-motion

Dragging the slider to a new value while a previous move is still running
is handled cleanly: the in-flight move is cancelled, the position is
corrected to reflect only the presses that actually fired, the source is
sent a `stop_cover`, and the new move starts from the corrected position.
The same happens if you call `position_tracker.set_position` while a move
is in flight (the manual value wins).

There may be a small residual error (~1 press worth) at the moment of
cancellation, because the press in flight when you re-targeted may or may
not have fully completed. Snap to a known value when convenient if it
drifts.

## Versions

- **v0.4.0**: Properly cancel/supersede an in-flight slider move when a new
  target arrives; correct position on cancellation; non-breaking.
- **v0.3.1**: Fix options-flow 500 error; fix slider snap-back via
  optimistic update.
- **v0.3.0**: Switch from 0–100% to degrees with per-motor `max_angle`
  (breaking — re-add the integration).
- **v0.2.0**: Switch from cover entities to number entities (breaking).
- **v0.1.x**: Initial cover-based implementation.

### Migrating from v0.2.x or earlier

After updating in HACS and restarting, old entities will become orphaned.
Remove the existing Position Tracker config entry and add it again — the
setup wizard now asks for `max_angle` per motor. (v0.3.x → v0.4.0 is a
plain update, no re-add needed.)

## License

MIT.
