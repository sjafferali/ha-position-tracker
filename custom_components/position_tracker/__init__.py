"""The Position Tracker integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_POSITION_VALUE,
    DOMAIN,
    SERVICE_SET_POSITION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.NUMBER]

SET_POSITION_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required(ATTR_POSITION_VALUE): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Position Tracker integration (service registration)."""
    hass.data.setdefault(DOMAIN, {})

    async def handle_set_position(call: ServiceCall) -> None:
        """Manually sync a tracked cover's position to a known value."""
        entity_id: str = call.data["entity_id"]
        position: int = call.data[ATTR_POSITION_VALUE]

        for entry_data in hass.data.get(DOMAIN, {}).values():
            for tracked in entry_data.get("entities", []):
                if tracked.entity_id == entity_id:
                    await tracked.async_sync_position(position)
                    return

        _LOGGER.warning(
            "position_tracker.set_position: unknown entity %s", entity_id
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_POSITION,
        handle_set_position,
        schema=SET_POSITION_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Position Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"entities": []}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
