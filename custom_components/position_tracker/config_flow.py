"""Config flow for Position Tracker."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    CONF_COVERS,
    CONF_DEVICE_NAME,
    CONF_INITIAL_POSITION,
    CONF_NAME,
    CONF_PRESSES_TO_FULL,
    CONF_SOURCE_ENTITY,
    DEFAULT_INITIAL_POSITION,
    DEFAULT_PRESSES_TO_FULL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class PositionTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup flow: name the device, add one or more tracked covers."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize state for the multi-step flow."""
        self._device_name: str | None = None
        self._covers: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: ask for the device name."""
        if user_input is not None:
            self._device_name = user_input[CONF_DEVICE_NAME].strip()
            if not self._device_name:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._user_schema(),
                    errors={CONF_DEVICE_NAME: "empty_name"},
                )
            return await self.async_step_add_cover()

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(),
        )

    @staticmethod
    def _user_schema() -> vol.Schema:
        return vol.Schema({vol.Required(CONF_DEVICE_NAME): TextSelector()})

    async def async_step_add_cover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: add a tracked cover."""
        errors: dict[str, str] = {}

        if user_input is not None:
            source = user_input[CONF_SOURCE_ENTITY]
            name = user_input[CONF_NAME].strip()

            if not name:
                errors[CONF_NAME] = "empty_name"
            elif any(c[CONF_SOURCE_ENTITY] == source for c in self._covers):
                errors[CONF_SOURCE_ENTITY] = "duplicate_source"
            elif self.hass.states.get(source) is None:
                errors[CONF_SOURCE_ENTITY] = "entity_not_found"
            elif not source.startswith("cover."):
                errors[CONF_SOURCE_ENTITY] = "not_a_cover"

            if not errors:
                self._covers.append(
                    {
                        CONF_NAME: name,
                        CONF_SOURCE_ENTITY: source,
                        CONF_PRESSES_TO_FULL: int(user_input[CONF_PRESSES_TO_FULL]),
                        CONF_INITIAL_POSITION: int(
                            user_input.get(
                                CONF_INITIAL_POSITION, DEFAULT_INITIAL_POSITION
                            )
                        ),
                    }
                )
                return await self.async_step_menu()

        return self.async_show_form(
            step_id="add_cover",
            data_schema=self._add_cover_schema(),
            errors=errors,
            description_placeholders={"device_name": self._device_name or ""},
        )

    @staticmethod
    def _add_cover_schema() -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_NAME): TextSelector(),
                vol.Required(CONF_SOURCE_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="cover")
                ),
                vol.Required(
                    CONF_PRESSES_TO_FULL, default=DEFAULT_PRESSES_TO_FULL
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=200, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_INITIAL_POSITION, default=DEFAULT_INITIAL_POSITION
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=100, step=1, mode=NumberSelectorMode.SLIDER
                    )
                ),
            }
        )

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: add another cover or finish."""
        return self.async_show_menu(
            step_id="menu",
            menu_options=["add_cover", "finish"],
            description_placeholders={
                "count": str(len(self._covers)),
                "names": ", ".join(c[CONF_NAME] for c in self._covers),
            },
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: create the config entry."""
        if not self._covers:
            return self.async_abort(reason="no_covers")

        return self.async_create_entry(
            title=self._device_name or "Position Tracker",
            data={
                CONF_DEVICE_NAME: self._device_name,
                CONF_COVERS: self._covers,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return PositionTrackerOptionsFlow(config_entry)


class PositionTrackerOptionsFlow(OptionsFlow):
    """Edit per-cover calibration after initial setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Capture the entry being edited."""
        self.config_entry = config_entry
        self._covers: list[dict[str, Any]] = [
            dict(c) for c in config_entry.data.get(CONF_COVERS, [])
        ]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit presses_to_full_travel for each configured cover."""
        if user_input is not None:
            for idx, cover in enumerate(self._covers):
                key = f"presses_{idx}"
                if key in user_input:
                    cover[CONF_PRESSES_TO_FULL] = int(user_input[key])

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    CONF_DEVICE_NAME: self.config_entry.data[CONF_DEVICE_NAME],
                    CONF_COVERS: self._covers,
                },
            )
            return self.async_create_entry(title="", data={})

        schema_dict: dict[Any, Any] = {}
        for idx, cover in enumerate(self._covers):
            schema_dict[
                vol.Required(
                    f"presses_{idx}",
                    default=cover[CONF_PRESSES_TO_FULL],
                )
            ] = NumberSelector(
                NumberSelectorConfig(
                    min=1, max=200, step=1, mode=NumberSelectorMode.BOX
                )
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "covers": "\n".join(
                    f"- {c[CONF_NAME]} ({c[CONF_SOURCE_ENTITY]})"
                    for c in self._covers
                )
            },
        )
