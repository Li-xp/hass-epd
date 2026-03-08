"""Constants for EPD Display integration."""

DOMAIN = "epd_display"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_DEVICE_NAME = "device_name"
CONF_CANVAS = "canvas"
CONF_DRIVER = "driver"
CONF_DITHER_MODE = "dither_mode"
CONF_CONTRAST = "contrast"
CONF_DITHER_STRENGTH = "dither_strength"

DEFAULT_PORT = 8100
DEFAULT_DEVICE_NAME = "NRF_EPD_3D56"
DEFAULT_CANVAS = "7.5_800_480"
DEFAULT_DRIVER = "07"
DEFAULT_DITHER_MODE = "threeColor"
DEFAULT_CONTRAST = 1.0
DEFAULT_DITHER_STRENGTH = 1.0

CANVAS_OPTIONS = [
    "1.54_152_152", "1.54_200_200",
    "2.13_212_104", "2.13_250_122",
    "2.66_296_152",
    "2.9_296_128", "2.9_384_168",
    "3.5_384_184", "3.7_416_240", "3.97_800_480",
    "4.2_400_300",
    "5.79_792_272", "5.83_600_448", "5.83_648_480",
    "7.5_640_384", "7.5_800_480", "7.5_880_528",
    "10.2_960_640", "10.85_1360_480", "11.6_960_640",
    "4E_600_400", "7.3E6",
]

DITHER_MODES = [
    "blackWhiteColor",
    "threeColor",
    "fourColor",
    "sixColor",
]

# Service names
SERVICE_CONNECT = "connect"
SERVICE_DISCONNECT = "disconnect"
SERVICE_CLEAR = "clear"
SERVICE_REFRESH = "refresh"
SERVICE_SLEEP = "sleep"
SERVICE_SYNC_TIME = "sync_time"
SERVICE_SYS_RESET = "sys_reset"
SERVICE_DISPLAY_IMAGE = "display_image"
SERVICE_DISPLAY_URL = "display_url"
SERVICE_GENERATE_IMAGE = "generate_image"
SERVICE_RENDER_TEMPLATE = "render_template"

ATTR_IMAGE_PATH = "image_path"
ATTR_IMAGE_URL = "image_url"
ATTR_CANVAS = "canvas"
ATTR_DRIVER = "driver"
ATTR_DITHER_MODE = "dither_mode"
ATTR_CONTRAST = "contrast"
ATTR_DITHER_STRENGTH = "dither_strength"
ATTR_CLOCK_MODE = "mode"

# Image editor / template
ATTR_WIDTH = "width"
ATTR_HEIGHT = "height"
ATTR_BACKGROUND_COLOR = "background_color"
ATTR_BACKGROUND_IMAGE = "background_image"
ATTR_ELEMENTS = "elements"
ATTR_OUTPUT_FILENAME = "output_filename"
ATTR_TEMPLATE_NAME = "template_name"
ATTR_SEND_AFTER = "send_after_render"

TEMPLATES_SUBDIR = "epd_templates"
IMAGES_SUBDIR = "epd_images"
