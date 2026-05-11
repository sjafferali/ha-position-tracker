# Position Tracker

A Home Assistant custom integration that adds **synthetic 0–100% position
tracking** to `cover` entities that don't have native position feedback. It
exposes the position as a `number` entity (slider) — same UX shape as
Eight Sleep base controls.

## What it's for

Some cover entities (adjustable beds, RF blinds, time-controlled garage
doors, etc.) accept open / close / stop commands but never tell you *where*
the motor is. This integration wraps such a cover with a new `number`
entity that:

- Counts every open / close press issued against the source
- Multiplies by a calibrated per-press delta (`100 / presses_to_full_travel`)
- Exposes the result as a 0–100% slider you can both read and drag
- Forwards drag-to-set into the right number of presses on the source

## How it counts presses

Listens to `EVENT_CALL_SERVICE` for `cover.open_cover` / `cover.close_cover`
calls targeting the source entity. Each call = one press.

It does **not** rely on source-cover state transitions for counting, because
back-to-back presses can leave the source's state at `opening` continuously,
and HA suppresses duplicate state events. Source state *is* used to update
the `move_direction` and `is_moving` attributes.

## Limitations

- **No ground truth.** If the source cover is moved by another path the
  integration can't observe (e.g., a physical remote on the bed), position
  drifts. Use the `position_tracker.set_position` service to re-sync.
- **End-stop overrun.** Pressing past the mechanical limit still counts as a
  press, so position estimates exceed reality at the extremes. Clamped to
  0–100, but the over-count silently inflates `presses_since_sync`. Snap-to-
  zero on a Flat preset (via your own automation calling
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
2. Name the device (e.g., "Theater Bed Position")
3. For each motor you want to track:
   - Display name (e.g., "Back")
   - Source cover entity
   - Presses to full travel (calibration — see below)
   - Initial position (default 0)
4. Click "Add another position" or "Finish"

You'll get one `number` entity per tracked motor, e.g.:
- `number.theater_bed_position_back`
- `number.theater_bed_position_legs`

### Calibrating "presses to full travel"

1. Move the source cover to fully closed (0%).
2. Tap **Up** on the source until fully open. Count your taps.
3. Use that number for "presses to full travel".

You can re-edit calibration any time via Settings → Devices & services →
Position Tracker → Configure.

## Service

### `position_tracker.set_position`

Manually snap a tracked number's position to a known value.

```yaml
service: position_tracker.set_position
data:
  entity_id: number.theater_bed_position_back
  position: 0
```

Recommended: wire this to your bed's Flat preset so position auto-snaps to
0 when you go flat.

## Status attributes

Every tracked number exposes:

| Attribute              | Meaning                                            |
| ---------------------- | -------------------------------------------------- |
| `source_entity`        | The wrapped cover entity ID                       |
| `presses_to_full`      | Calibration value                                 |
| `delta_per_press`      | `100 / presses_to_full`                           |
| `presses_since_sync`   | Press count since last manual sync (drift indicator) |
| `is_moving`            | True while source cover state is opening/closing  |
| `move_direction`       | "open", "close", or null                          |
| `last_sync_at`         | ISO timestamp of last `set_position` call         |
| `seconds_since_sync`   | Convenience derived value                         |

## Versions

- **v0.2.0**: Switch from cover entities to number entities (breaking).
- **v0.1.x**: Initial cover-based implementation. Deprecated.

### Migrating from v0.1.x

After updating in HACS and restarting:
1. Old `cover.<...>` entities will become orphaned/unavailable.
2. Re-add the integration via **Settings → Devices & services → + Add Integration → Position Tracker**, or just remove the old config entry and add a new one.
3. Update any dashboards/automations to point at `number.<...>` instead of `cover.<...>`.

## License

MIT.
