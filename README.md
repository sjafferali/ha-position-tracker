# Position Tracker

A Home Assistant custom integration that adds **synthetic 0–100% position
tracking** to `cover` entities that don't have native position feedback.

## What it's for

Some cover entities (adjustable beds, RF blinds, time-controlled garage
doors, etc.) report `opening` / `closing` states but never tell you *where*
they are. This integration wraps such a cover with a new entity that:

- Counts every open / close press
- Multiplies by a calibrated per-press delta (`100 / presses_to_full_travel`)
- Exposes the result as a real `current_cover_position`
- Forwards `open` / `close` / `stop` calls through to the source

The wrapper implements `set_cover_position`, so dragging the slider to "60%"
fires the right number of presses to get there.

## How it counts presses

Listens to `EVENT_CALL_SERVICE` for `cover.open_cover` / `cover.close_cover`
calls targeting the source entity. Each call = one press.

It does **not** rely on source-cover state transitions for counting, because
back-to-back presses can leave the source's state at `opening` continuously,
and HA suppresses duplicate state events. Source state *is* used to drive
`is_opening` / `is_closing` so the UI shows motion accurately.

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
3. For each cover you want to track:
   - Display name (e.g., "Back")
   - Source cover entity
   - Presses to full travel (calibration — see below)
   - Initial position (default 0)
4. Click "Add another cover" or "Finish"

### Calibrating "presses to full travel"

1. Move the source cover to fully closed (0%).
2. Tap **Up** on the source until fully open. Count your taps.
3. Use that number for "presses to full travel".

You can re-edit calibration any time via Settings → Devices & services →
Position Tracker → Configure.

## Service

### `position_tracker.set_position`

Manually snap a tracked cover's position to a known value.

```yaml
service: position_tracker.set_position
data:
  entity_id: cover.theater_bed_position_back
  position: 0
```

Recommended: wire this to your bed's Flat preset so position auto-snaps to
0 when you go flat.

## Status attributes

Every tracked cover exposes:

| Attribute              | Meaning                                            |
| ---------------------- | -------------------------------------------------- |
| `current_position`     | Estimated 0–100% (the cover's main value)         |
| `source_entity`        | The wrapped cover entity ID                       |
| `presses_to_full`      | Calibration value                                 |
| `delta_per_press`      | `100 / presses_to_full`                           |
| `presses_since_sync`   | Press count since last manual sync (drift indicator) |
| `last_sync_at`         | ISO timestamp of last `set_position` call         |
| `seconds_since_sync`   | Convenience derived value                          |

## License

MIT.
