"""Constants for the Position Tracker integration."""

from typing import Final

DOMAIN: Final = "position_tracker"

CONF_DEVICE_NAME: Final = "device_name"
CONF_COVERS: Final = "covers"
CONF_SOURCE_ENTITY: Final = "source_entity"
CONF_NAME: Final = "name"
CONF_PRESSES_TO_FULL: Final = "presses_to_full_travel"
CONF_MAX_ANGLE: Final = "max_angle"
CONF_INITIAL_POSITION: Final = "initial_position"

DEFAULT_PRESSES_TO_FULL: Final = 30
DEFAULT_MAX_ANGLE: Final = 45
DEFAULT_INITIAL_POSITION: Final = 0

SERVICE_SET_POSITION: Final = "set_position"
ATTR_POSITION_VALUE: Final = "position"

SOURCE_STATE_OPENING: Final = "opening"
SOURCE_STATE_CLOSING: Final = "closing"

# How long after a counted press to keep is_opening/is_closing true
# if no source state confirms motion ended.
MOVE_DIRECTION_TIMEOUT_S: Final = 2.0
