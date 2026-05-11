"""Number platform for Position Tracker.

Wraps an existing cover entity that lacks position feedback and synthesizes
a 0-100% position by counting how many open/close service calls have been
issued against the source entity, multiplied by a calibrated per-press
delta. Exposed as a number entity (slider) so the UX matches integrations
like Eight Sleep that surface bed angles as direct-set sliders.

Why service-call events instead of source state transitions
-----------------------------------------------------------
Two back-to-back presses can leave the source's state at "opening" the whole
time. Home Assistant suppresses state-changed events when the value is
unchanged, so a state-listener would see one event instead of two and
under-count. EVENT_CALL_SERVICE catches every press attempt regardless of
source state, including presses fired by us, by the source's own UI, by
automations, or by other integrations.

Source state transitions are still used, but only to set the `move_direction`
attribute for "moving right now" display.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_CALL_SERVICE, PERCENTAGE
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COVERS,
    CONF_DEVICE_NAME,
    CONF_INITIAL_POSITION,
    CONF_NAME,
    CONF_PRESSES_TO_FULL,
    CONF_SOURCE_ENTITY,
    DEFAULT_TOLERANCE,
    DOMAIN,
    MOVE_DIRECTION_TIMEOUT_S,
    SOURCE_STATE_CLOSING,
    SOURCE_STATE_OPENING,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Build a TrackedPositionNumber for each configured source cover."""
    device_name: str = entry.data[CONF_DEVICE_NAME]
    covers_config: list[dict[str, Any]] = entry.data.get(CONF_COVERS, [])

    entities: list[TrackedPositionNumber] = []
    for cfg in covers_config:
        entities.append(
            TrackedPositionNumber(
                entry_id=entry.entry_id,
                device_name=device_name,
                name=cfg[CONF_NAME],
                source_entity=cfg[CONF_SOURCE_ENTITY],
                presses_to_full=cfg[CONF_PRESSES_TO_FULL],
                initial_position=cfg.get(CONF_INITIAL_POSITION, 0),
            )
        )

    hass.data[DOMAIN][entry.entry_id]["entities"] = entities
    async_add_entities(entities)


class TrackedPositionNumber(NumberEntity, RestoreEntity):
    """Number entity that mirrors a source cover and tracks position via press counting."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:angle-acute"

    def __init__(
        self,
        entry_id: str,
        device_name: str,
        name: str,
        source_entity: str,
        presses_to_full: int,
        initial_position: int,
    ) -> None:
        """Initialize the tracked position number."""
        self._entry_id = entry_id
        self._device_name = device_name
        self._source_entity = source_entity
        self._presses_to_full = max(1, int(presses_to_full))
        self._delta_per_press = 100.0 / self._presses_to_full

        self._position: float = float(max(0, min(100, initial_position)))
        self._move_direction: str | None = None
        self._move_direction_timer: asyncio.TimerHandle | None = None

        self._presses_since_sync = 0
        self._last_sync_at: datetime | None = None

        self._attr_unique_id = (
            f"{entry_id}_{_slugify(source_entity)}_{_slugify(name)}"
        )
        # has_entity_name=True: HA will compose "<device> <name>" automatically
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": device_name,
            "manufacturer": "Position Tracker",
        }

        self._unsub_state = None
        self._unsub_service = None

    async def async_added_to_hass(self) -> None:
        """Restore last known position and subscribe to source signals."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in (None, "", "unknown", "unavailable"):
                try:
                    self._position = float(last_state.state)
                except (TypeError, ValueError):
                    pass

            sync_at = last_state.attributes.get("last_sync_at")
            if sync_at:
                try:
                    self._last_sync_at = dt_util.parse_datetime(sync_at)
                except (TypeError, ValueError):
                    pass

            since = last_state.attributes.get("presses_since_sync")
            if since is not None:
                try:
                    self._presses_since_sync = int(since)
                except (TypeError, ValueError):
                    pass

        self._unsub_state = async_track_state_change_event(
            self.hass,
            [self._source_entity],
            self._handle_source_state_change,
        )
        self._unsub_service = self.hass.bus.async_listen(
            EVENT_CALL_SERVICE, self._handle_service_call
        )

    async def async_will_remove_from_hass(self) -> None:
        """Tear down subscriptions."""
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_service is not None:
            self._unsub_service()
            self._unsub_service = None
        if self._move_direction_timer is not None:
            self._move_direction_timer.cancel()
            self._move_direction_timer = None
        await super().async_will_remove_from_hass()

    # Press counting (primary position update path)

    @callback
    def _handle_service_call(self, event: Event) -> None:
        """Count source-cover open/close service calls as presses."""
        data = event.data
        if data.get("domain") != "cover":
            return
        service = data.get("service")
        if service not in ("open_cover", "close_cover"):
            return
        if not _service_targets_entity(data, self._source_entity):
            return
        direction = "open" if service == "open_cover" else "close"
        self._count_press(direction)

    def _count_press(self, direction: str) -> None:
        """Apply a single press worth of motion to position."""
        if direction == "open":
            self._position = min(100.0, self._position + self._delta_per_press)
        else:
            self._position = max(0.0, self._position - self._delta_per_press)

        self._presses_since_sync += 1
        self._move_direction = direction

        if self._move_direction_timer is not None:
            self._move_direction_timer.cancel()
        self._move_direction_timer = self.hass.loop.call_later(
            MOVE_DIRECTION_TIMEOUT_S, self._clear_move_direction
        )

        _LOGGER.debug(
            "%s: counted %s press, position=%.1f, presses_since_sync=%d",
            self.entity_id, direction, self._position, self._presses_since_sync,
        )
        self.async_write_ha_state()

    @callback
    def _clear_move_direction(self) -> None:
        """Fallback clear of move direction on timeout."""
        self._move_direction = None
        self._move_direction_timer = None
        self.async_write_ha_state()

    # Source state observation (drives move_direction attribute)

    @callback
    def _handle_source_state_change(self, event: Event) -> None:
        """Update move_direction from source state."""
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return
        value = new_state.state
        if value == SOURCE_STATE_OPENING:
            new_dir = "open"
        elif value == SOURCE_STATE_CLOSING:
            new_dir = "close"
        else:
            new_dir = None

        if new_dir != self._move_direction:
            self._move_direction = new_dir
            if new_dir is not None and self._move_direction_timer is not None:
                self._move_direction_timer.cancel()
                self._move_direction_timer = None
            self.async_write_ha_state()

    # NumberEntity contract

    @property
    def native_value(self) -> float:
        """Return current estimated position 0-100."""
        return float(round(self._position))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Diagnostic and configuration attributes."""
        attrs: dict[str, Any] = {
            "source_entity": self._source_entity,
            "presses_to_full": self._presses_to_full,
            "delta_per_press": round(self._delta_per_press, 2),
            "presses_since_sync": self._presses_since_sync,
            "is_moving": self._move_direction is not None,
            "move_direction": self._move_direction,
        }
        if self._last_sync_at is not None:
            attrs["last_sync_at"] = self._last_sync_at.isoformat()
            attrs["seconds_since_sync"] = int(
                (dt_util.utcnow() - self._last_sync_at).total_seconds()
            )
        return attrs

    async def async_set_native_value(self, value: float) -> None:
        """Move toward target position via open-loop press calculation.

        delta := target - current
        presses := round(|delta| / delta_per_press), at least 1 if past tolerance
        Issues that many open or close service calls in sequence on the source
        cover. Each call is awaited so the source's pulse burst completes
        before the next; the press counter updates via the service-call
        listener as each call goes by.
        """
        target = float(value)
        delta = target - self._position

        if abs(delta) < DEFAULT_TOLERANCE:
            _LOGGER.debug(
                "%s: set %s within tolerance of current %.1f, no-op",
                self.entity_id, target, self._position,
            )
            return

        presses = max(1, int(round(abs(delta) / self._delta_per_press)))
        service = "open_cover" if delta > 0 else "close_cover"

        _LOGGER.info(
            "%s: set %s -> firing %d %s calls (current %.1f, delta %.1f)",
            self.entity_id, target, presses, service, self._position, delta,
        )

        for _ in range(presses):
            await self.hass.services.async_call(
                "cover",
                service,
                {"entity_id": self._source_entity},
                blocking=True,
            )

    # Service-callable helpers

    async def async_sync_position(self, position: float) -> None:
        """Snap position to a known value (called by the set_position service)."""
        clamped = max(0.0, min(100.0, float(position)))
        _LOGGER.info(
            "%s: synced position %.1f -> %.1f",
            self.entity_id, self._position, clamped,
        )
        self._position = clamped
        self._presses_since_sync = 0
        self._last_sync_at = dt_util.utcnow()
        self.async_write_ha_state()


def _service_targets_entity(service_event_data: dict, entity_id: str) -> bool:
    """Return True if a call_service event's payload targets the given entity."""
    service_data = service_event_data.get("service_data") or {}

    candidates: list[Any] = []
    if "entity_id" in service_data:
        candidates.append(service_data["entity_id"])

    target = service_event_data.get("target") or service_data.get("target") or {}
    if isinstance(target, dict) and "entity_id" in target:
        candidates.append(target["entity_id"])

    for c in candidates:
        if isinstance(c, str):
            if c == entity_id:
                return True
        elif isinstance(c, (list, tuple, set)):
            if entity_id in c:
                return True
    return False


def _slugify(s: str) -> str:
    """Lowercase + replace dots and spaces; sufficient for unique IDs."""
    return s.replace(".", "_").replace(" ", "_").lower()
