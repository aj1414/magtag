# SPDX-FileCopyrightText: 2024 Carter Nelson for Adafruit Industries
#
# SPDX-License-Identifier: MIT
# pylint: disable=redefined-outer-name, wrong-import-order, unsubscriptable-object

import time
import alarm
import board
import terminalio
import displayio
import adafruit_imageload
from adafruit_display_text import label
from adafruit_magtag.magtag import MagTag

# Import configuration and secrets
try:
    from secrets import secrets
    APPID = secrets.get('openweather_token', '')
except ImportError:
    print("ERROR: secrets.py not found!")
    APPID = ""

try:
    from config import (
        LAT, LON, TMZ, CITY, METRIC, SLEEP_TIME,
        BATTERY_CRITICAL_VOLTAGE, BATTERY_MINIMUM_VOLTAGE,
        EV_ENABLED, GREENHOUSE_ENABLED, RUNNING_ENABLED
    )
except ImportError:
    print("ERROR: config.py not found! Using defaults.")
    LAT = 42.5236
    LON = -71.1030
    TMZ = "America/New_York"
    CITY = "Boston"
    METRIC = False
    SLEEP_TIME = 60 * 60
    BATTERY_CRITICAL_VOLTAGE = 3.0
    BATTERY_MINIMUM_VOLTAGE = 2.0
    EV_ENABLED = False
    GREENHOUSE_ENABLED = False
    RUNNING_ENABLED = False

# Get API URLs from secrets
EV_API_URL = secrets.get('ev_api_url', '') if EV_ENABLED else ''
GREENHOUSE_API_URL = secrets.get('greenhouse_api_url', '') if GREENHOUSE_ENABLED else ''
GREENHOUSE_HISTORY_API_URL = secrets.get('greenhouse_history_api_url', '') if GREENHOUSE_ENABLED else ''
GREENHOUSE_PLUGS_API_URL = secrets.get('greenhouse_plugs_api_url', '') if GREENHOUSE_ENABLED else ''
RUNNING_API_URL = secrets.get('running_api_url', '') if RUNNING_ENABLED else ''

# -------------------------------------------
# Constants
# -------------------------------------------
SECONDS_PER_HOUR = 60 * 60
SECONDS_PER_MINUTE = 60
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR
WAKE_TIME_HOUR = 3
WAKE_TIME_MINUTE = 15
WAKE_TIME_SECONDS = (WAKE_TIME_HOUR * SECONDS_PER_HOUR) + (WAKE_TIME_MINUTE * SECONDS_PER_MINUTE)

# Display refresh delay
DISPLAY_REFRESH_DELAY = 1  # seconds

# LED flash settings
LED_FLASH_DURATION = 0.05  # seconds
LED_FLASH_INTERVAL = 0.5  # seconds (reduced from 3 to save battery)
LED_FLASH_COUNT = 5  # reduced from 1000 to prevent battery drain

# UI positioning constants
DATE_POSITION_X = 15
DATE_POSITION_Y = 14
LOCATION_POSITION_X = 15
LOCATION_POSITION_Y = 25
ICON_POSITION_X = 10
ICON_POSITION_Y = 40
LOW_TEMP_POSITION_X = 122
LOW_TEMP_POSITION_Y = 60
HIGH_TEMP_POSITION_X = 162
HIGH_TEMP_POSITION_Y = 60
WIND_POSITION_X = 110
WIND_POSITION_Y = 95
SUNRISE_POSITION_X = 45
SUNRISE_POSITION_Y = 117
SUNSET_POSITION_X = 130
SUNSET_POSITION_Y = 117
FUTURE_BANNER_LEFT = 206

# -------------------------------------------

# ----------------------------
# Define various assets
# ----------------------------
BACKGROUND_BMP = "/bmps/weather_bg.bmp"
ICONS_LARGE_FILE = "/bmps/weather_icons_70px.bmp"
ICONS_SMALL_FILE = "/bmps/weather_icons_20px.bmp"
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Weather Code Information from https://open-meteo.com/en/docs
# Code 	Description
# 0 	Clear sky
# 1, 2, 3 	Mainly clear, partly cloudy, and overcast
# 45, 48 	Fog and depositing rime fog
# 51, 53, 55 	Drizzle: Light, moderate, and dense intensity
# 56, 57 	Freezing Drizzle: Light and dense intensity
# 61, 63, 65 	Rain: Slight, moderate and heavy intensity
# 66, 67 	Freezing Rain: Light and heavy intensity
# 71, 73, 75 	Snow fall: Slight, moderate, and heavy intensity
# 77 	Snow grains
# 80, 81, 82 	Rain showers: Slight, moderate, and violent
# 85, 86 	Snow showers slight and heavy
# 95 * 	Thunderstorm: Slight or moderate
# 96, 99 * 	Thunderstorm with slight and heavy hail

# Map the above WMO codes to index of icon in 3x3 spritesheet
WMO_CODE_TO_ICON = (
    (0,),  # 0 = sunny
    (1,),  # 1 = partly sunny/cloudy
    (2,),  # 2 = cloudy
    (3,),  # 3 = very cloudy
    (61, 63, 65),  # 4 = rain
    (51, 53, 55, 80, 81, 82),  # 5 = showers
    (95, 96, 99),  # 6 = storms
    (56, 57, 66, 67, 71, 73, 75, 77, 85, 86),  # 7 = snow
    (45, 48),  # 8 = fog and stuff
)

# /////////////////////////////////////////////////////////////////////////
#  Deep sleep with timer + button wake
# /////////////////////////////////////////////////////////////////////////


def go_to_sleep_with_alarms():
    """Enter deep sleep with timer and button wake alarms."""
    print(
        "Sleeping for {} hours, {} minutes".format(
            SLEEP_TIME // SECONDS_PER_HOUR,
            (SLEEP_TIME // SECONDS_PER_MINUTE) % 60
        )
    )

    # Disable peripherals to save power
    magtag.peripherals.neopixel_disable = True

    # Release button pins so they can be used as alarm sources
    magtag.peripherals.deinit()

    # Wake on timer, D11 (greenhouse plot), D14 (running stats), or D15 (weather refresh)
    time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + SLEEP_TIME)
    pin_alarm_d11 = alarm.pin.PinAlarm(pin=board.D11, value=False, pull=True)
    pin_alarm_d14 = alarm.pin.PinAlarm(pin=board.D14, value=False, pull=True)
    pin_alarm_d15 = alarm.pin.PinAlarm(pin=board.D15, value=False, pull=True)

    alarm.exit_and_deep_sleep_until_alarms(time_alarm, pin_alarm_d11, pin_alarm_d14, pin_alarm_d15)


# /////////////////////////////////////////////////////////////////////////
#  Initialize MagTag and check wake reason
# /////////////////////////////////////////////////////////////////////////

magtag = MagTag()

# Check what woke us from deep sleep
wake_alarm = alarm.wake_alarm
if isinstance(wake_alarm, alarm.pin.PinAlarm) and wake_alarm.pin == board.D11 and GREENHOUSE_ENABLED:
    print("Woke from button D11 (right) -- showing greenhouse plot")
    # Warm up network — first fetch after deep sleep initializes socket pool
    for _attempt in range(5):
        try:
            print("Network warm-up (attempt {})...".format(_attempt + 1))
            resp = magtag.network.fetch(GREENHOUSE_API_URL)
            resp.close()
            print("Network ready")
            break
        except Exception as e:
            print("Warm-up attempt {} failed: {}".format(_attempt + 1, e))
            time.sleep(5)
    # Lazy-import plot module to save RAM on normal weather path
    import greenhouse_plot
    greenhouse_plot.show(magtag, GREENHOUSE_HISTORY_API_URL, DISPLAY_REFRESH_DELAY)
    go_to_sleep_with_alarms()
    # Code never reaches here -- deep sleep restarts from beginning

if isinstance(wake_alarm, alarm.pin.PinAlarm) and wake_alarm.pin == board.D14 and RUNNING_ENABLED:
    print("Woke from button D14 -- showing running stats")
    # Warm up network — first fetch after deep sleep initializes socket pool
    for _attempt in range(5):
        try:
            print("Network warm-up (attempt {})...".format(_attempt + 1))
            resp = magtag.network.fetch(RUNNING_API_URL)
            resp.close()
            print("Network ready")
            break
        except Exception as e:
            print("Warm-up attempt {} failed: {}".format(_attempt + 1, e))
            time.sleep(5)
    # Lazy-import display module to save RAM on normal weather path
    import running_display
    running_display.show(magtag, RUNNING_API_URL, DISPLAY_REFRESH_DELAY)
    go_to_sleep_with_alarms()
    # Code never reaches here -- deep sleep restarts from beginning

# ----------------------------
# Normal weather display path
# ----------------------------

# ----------------------------
# Background bitmap
# ----------------------------
magtag.graphics.set_background(BACKGROUND_BMP)

# ----------------------------
# Weather icons sprite sheet
# ----------------------------
icons_large_bmp, icons_large_pal = adafruit_imageload.load(ICONS_LARGE_FILE)
icons_small_bmp, icons_small_pal = adafruit_imageload.load(ICONS_SMALL_FILE)

# /////////////////////////////////////////////////////////////////////////
#  Helper functions
# /////////////////////////////////////////////////////////////////////////


def get_current():
    """
    Fetch current weather data from OpenWeatherMap API.

    Returns:
        Response object containing current weather data

    Raises:
        RuntimeError: If network request fails
    """
    url = "https://api.openweathermap.org/data/3.0/onecall"
    url += f"?lat={LAT}&lon={LON}&appid={APPID}"

    try:
        resp = magtag.network.fetch(url)
        return resp
    except (RuntimeError, OSError) as error:
        print(f"Error fetching current weather: {error}")
        raise


def get_forecast():
    """
    Fetch weather forecast data from Open-Meteo API.

    Returns:
        Response object containing forecast data for the next several days

    Raises:
        RuntimeError: If network request fails
    """
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&"
    url += "daily=weather_code,temperature_2m_max,temperature_2m_min"
    url += ",sunrise,sunset,wind_speed_10m_max,wind_direction_10m_dominant"
    url += "&timeformat=unixtime"
    url += f"&timezone={TMZ}"
    print(url)

    try:
        resp = magtag.network.fetch(url)
        return resp
    except (RuntimeError, OSError) as error:
        print(f"Error fetching forecast: {error}")
        raise


def get_ev_status():
    """
    Fetch EV charging status from local Kona API server.

    Returns:
        dict: EV status data or None if fetch fails
    """
    if not EV_API_URL:
        return None

    try:
        print(f"Fetching EV status from {EV_API_URL}")
        resp = magtag.network.fetch(EV_API_URL)
        return resp.json()
    except (RuntimeError, OSError) as error:
        print(f"Error fetching EV status: {error}")
        return None


def make_ev_banner(x=0, y=0):
    """
    Create display banner for EV status information.

    Args:
        x: X position of the banner
        y: Y position of the banner

    Returns:
        displayio.Group containing EV status label
    """
    ev_line = label.Label(terminalio.FONT, text="EV: --", color=0x000000)
    ev_line.anchor_point = (0, 0.5)
    ev_line.anchored_position = (0, 10)

    group = displayio.Group(x=x, y=y)
    group.append(ev_line)
    return group


def update_ev_status(ev_battery_banner, ev_charge_banner, data):
    """
    Update EV status information on the display.

    Args:
        ev_battery_banner: Display group for battery status
        ev_charge_banner: Display group for charging status
        data: EV status data dictionary from API
    """
    if data is None:
        ev_battery_banner[0].text = "EV: offline"
        ev_charge_banner[0].text = ""
        return

    battery = data.get("battery", "--")
    charging = data.get("charging", False)

    # Format battery line
    if isinstance(battery, (int, float)):
        ev_battery_banner[0].text = f"EV: {battery:.0f}%"
    else:
        ev_battery_banner[0].text = "EV: --%"

    # Format charging status line
    if charging:
        ev_charge_banner[0].text = "Charging"
    else:
        ev_charge_banner[0].text = "Not Charging"


def get_greenhouse_status():
    """
    Fetch greenhouse temp/humidity from local API server.

    Returns:
        dict: Greenhouse data or None if fetch fails
    """
    if not GREENHOUSE_API_URL:
        return None

    try:
        print(f"Fetching greenhouse status from {GREENHOUSE_API_URL}")
        resp = magtag.network.fetch(GREENHOUSE_API_URL)
        return resp.json()
    except (RuntimeError, OSError) as error:
        print(f"Error fetching greenhouse status: {error}")
        return None


def make_greenhouse_banner(x=0, y=0):
    """
    Create display banner for greenhouse information.

    Args:
        x: X position of the banner
        y: Y position of the banner

    Returns:
        displayio.Group containing greenhouse temp/humidity label
    """
    gh_line = label.Label(terminalio.FONT, text="GH: --", color=0x000000)
    gh_line.anchor_point = (0, 0.5)
    gh_line.anchored_position = (0, 10)

    group = displayio.Group(x=x, y=y)
    group.append(gh_line)
    return group


def update_greenhouse_status(gh_banner, data):
    """
    Update greenhouse status information on the display.

    Args:
        gh_banner: Display group for greenhouse data
        data: Greenhouse data dictionary from API
    """
    if data is None:
        gh_banner[0].text = "GH: offline"
        return

    temp_f = data.get("temperature_f", "--")
    humidity = data.get("humidity", "--")

    # Format combined temperature and humidity line
    if isinstance(temp_f, (int, float)) and isinstance(humidity, (int, float)):
        gh_banner[0].text = f"GH: {temp_f:.0f}F  {humidity:.0f}%"
    elif isinstance(temp_f, (int, float)):
        gh_banner[0].text = f"GH: {temp_f:.0f}F  --%"
    elif isinstance(humidity, (int, float)):
        gh_banner[0].text = f"GH: --F  {humidity:.0f}%"
    else:
        gh_banner[0].text = "GH: --F  --%"


def get_plug_status():
    """Fetch smart plug status from local API server."""
    if not GREENHOUSE_PLUGS_API_URL:
        return None
    try:
        resp = magtag.network.fetch(GREENHOUSE_PLUGS_API_URL)
        return resp.json()
    except (RuntimeError, OSError) as error:
        print(f"Error fetching plug status: {error}")
        return None


def make_plug_banner(x=0, y=0):
    """Create display banner for smart plug status."""
    plug_line = label.Label(terminalio.FONT, text="", color=0x000000)
    plug_line.anchor_point = (0, 0.5)
    plug_line.anchored_position = (0, 10)
    group = displayio.Group(x=x, y=y)
    group.append(plug_line)
    return group


def update_plug_status(plug_banner, data):
    """Update plug status on display."""
    if data is None:
        plug_banner[0].text = ""
        return
    heater = data.get("heater", {})
    light = data.get("light", {})
    h_str = "On" if heater.get("on") else "Off"
    l_str = "On" if light.get("on") else "Off"
    plug_banner[0].text = f"H:{h_str}  L:{l_str}"


def make_banner(x=0, y=0):
    """
    Create a display banner for future forecast information.

    Args:
        x: X position of the banner
        y: Y position of the banner

    Returns:
        displayio.Group containing day of week label, weather icon, and temperature
    """
    day_of_week = label.Label(terminalio.FONT, text="DAY", color=0x000000)
    day_of_week.anchor_point = (0, 0.5)
    day_of_week.anchored_position = (0, 10)

    icon = displayio.TileGrid(
        icons_small_bmp,
        pixel_shader=icons_small_pal,
        x=25,
        y=0,
        width=1,
        height=1,
        tile_width=20,
        tile_height=20,
    )

    day_temp = label.Label(terminalio.FONT, text="+100F", color=0x000000)
    day_temp.anchor_point = (0, 0.5)
    day_temp.anchored_position = (50, 10)

    group = displayio.Group(x=x, y=y)
    group.append(day_of_week)
    group.append(icon)
    group.append(day_temp)

    return group


def temperature_text(temp_celsius):
    """
    Convert temperature to display string in Celsius or Fahrenheit.

    Args:
        temp_celsius: Temperature in Celsius

    Returns:
        Formatted temperature string
    """
    if METRIC:
        return "{:3.0f}C".format(temp_celsius)
    else:
        return "{:3.0f}".format(32.0 + 1.8 * temp_celsius)


def wind_text(speed_kmh, direction):
    """
    Format wind speed and direction as display string.

    Args:
        speed_kmh: Wind speed in kilometers per hour
        direction: Wind direction in degrees (0-360)

    Returns:
        Formatted wind string (e.g., "from NW 15mph")
    """
    # Convert degrees to cardinal direction (more elegant approach)
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    idx = round(direction / 45) % 8
    wind_dir = directions[idx]

    wtext = f"from {wind_dir} "

    if METRIC:
        wtext += "{:2.0f}kmh".format(speed_kmh)
    else:
        wtext += "{:2.0f}mph".format(0.621371 * speed_kmh)
    return wtext


def update_today(data):
    """
    Update today's weather information on the display.

    Args:
        data: Weather forecast data dictionary from API
    """
    # Date text
    timestamp = data["daily"]["time"][0] + data["utc_offset_seconds"]
    date_time = time.localtime(timestamp)

    voltage = magtag.peripherals.battery

    today_date.text = "{} {:.5} {}, {:.2f}V".format(
        DAYS[date_time.tm_wday].upper(),
        MONTHS[date_time.tm_mon - 1].upper(),
        date_time.tm_mday,
        voltage
    )

    # Weather icon
    weather_code = data["daily"]["weather_code"][0]
    today_icon[0] = next(i for i, t in enumerate(WMO_CODE_TO_ICON) if weather_code in t)

    # Temperatures
    today_low_temp.text = temperature_text(data["daily"]["temperature_2m_min"][0])
    today_high_temp.text = temperature_text(data["daily"]["temperature_2m_max"][0])

    # Wind
    wind_speed = data["daily"]["wind_speed_10m_max"][0]
    wind_direction = data["daily"]["wind_direction_10m_dominant"][0]
    today_wind.text = wind_text(wind_speed, wind_direction)

    # Sunrise/sunset times
    sunrise_time = time.localtime(data["daily"]["sunrise"][0] + data["utc_offset_seconds"])
    sunset_time = time.localtime(data["daily"]["sunset"][0] + data["utc_offset_seconds"])

    # Format sunrise (handle 12-hour format properly)
    sr_hour = sunrise_time.tm_hour
    sr_period = "AM" if sr_hour < 12 else "PM"
    sr_display_hour = sr_hour if sr_hour <= 12 else sr_hour - 12
    sr_display_hour = 12 if sr_display_hour == 0 else sr_display_hour
    today_sunrise.text = "{:2d}:{:02d} {}".format(sr_display_hour, sunrise_time.tm_min, sr_period)

    # Format sunset (handle 12-hour format properly)
    ss_hour = sunset_time.tm_hour
    ss_period = "AM" if ss_hour < 12 else "PM"
    ss_display_hour = ss_hour if ss_hour <= 12 else ss_hour - 12
    ss_display_hour = 12 if ss_display_hour == 0 else ss_display_hour
    today_sunset.text = "{:2d}:{:02d} {}".format(ss_display_hour, sunset_time.tm_min, ss_period)


def update_future(data):
    """
    Update future forecast information on the display.

    Args:
        data: Weather forecast data dictionary from API
    """
    for i, banner in enumerate(future_banners):
        # Day of week
        timestamp = data["daily"]["time"][i + 1] + data["utc_offset_seconds"]
        date_time = time.localtime(timestamp)
        banner[0].text = DAYS[date_time.tm_wday][:3].upper()

        # Weather icon
        weather_code = data["daily"]["weather_code"][i + 1]
        banner[1][0] = next(x for x, t in enumerate(WMO_CODE_TO_ICON) if weather_code in t)

        # Temperature (high and low)
        temp_max = data["daily"]["temperature_2m_max"][i + 1]
        temp_min = data["daily"]["temperature_2m_min"][i + 1]
        banner[2].text = temperature_text(temp_max) + temperature_text(temp_min)


# ===========
# U I
# ===========

print("Fetching current...")
try:
    resp_data = get_current()
    current_data = resp_data.json()
    current_temp_F = 9 / 5 * (current_data["current"]["temp"] - 273.15) + 32
    current_humidity = current_data["current"]["humidity"]
except (RuntimeError, OSError, KeyError) as error:
    print(f"Error getting current weather: {error}")
    # Set defaults if fetch fails
    current_temp_F = 0
    current_humidity = 0

today_date = label.Label(terminalio.FONT, text="?" * 30, color=0x000000)
today_date.anchor_point = (0, 0)
today_date.anchored_position = (DATE_POSITION_X, DATE_POSITION_Y)

location_name = label.Label(terminalio.FONT, color=0x000000)
if CITY:
    location_name.text = f"{CITY[:16]} Temp: "
    location_name.text += f"{current_temp_F:.1f} "
    location_name.text += "Humid: "
    location_name.text += f"{current_humidity:.1f}"
else:
    location_name.text = f"({LAT},{LON})"

location_name.anchor_point = (0, 0)
location_name.anchored_position = (LOCATION_POSITION_X, LOCATION_POSITION_Y)

today_icon = displayio.TileGrid(
    icons_large_bmp,
    pixel_shader=icons_small_pal,
    x=ICON_POSITION_X,
    y=ICON_POSITION_Y,
    width=1,
    height=1,
    tile_width=70,
    tile_height=70,
)

today_low_temp = label.Label(terminalio.FONT, text="+100F", color=0x000000)
today_low_temp.anchor_point = (0.5, 0)
today_low_temp.anchored_position = (LOW_TEMP_POSITION_X, LOW_TEMP_POSITION_Y)

today_high_temp = label.Label(terminalio.FONT, text="+100F", color=0x000000)
today_high_temp.anchor_point = (0.5, 0)
today_high_temp.anchored_position = (HIGH_TEMP_POSITION_X, HIGH_TEMP_POSITION_Y)

today_wind = label.Label(terminalio.FONT, text="99m/s", color=0x000000)
today_wind.anchor_point = (0, 0.5)
today_wind.anchored_position = (WIND_POSITION_X, WIND_POSITION_Y)

today_sunrise = label.Label(terminalio.FONT, text="12:12 PM", color=0x000000)
today_sunrise.anchor_point = (0, 0.5)
today_sunrise.anchored_position = (SUNRISE_POSITION_X, SUNRISE_POSITION_Y)

today_sunset = label.Label(terminalio.FONT, text="12:12 PM", color=0x000000)
today_sunset.anchor_point = (0, 0.5)
today_sunset.anchored_position = (SUNSET_POSITION_X, SUNSET_POSITION_Y)

today_banner = displayio.Group()
today_banner.append(today_date)
today_banner.append(location_name)
today_banner.append(today_icon)
today_banner.append(today_low_temp)
today_banner.append(today_high_temp)
today_banner.append(today_wind)
today_banner.append(today_sunrise)
today_banner.append(today_sunset)

future_banners = [
    make_banner(x=FUTURE_BANNER_LEFT, y=18),
    make_banner(x=FUTURE_BANNER_LEFT, y=39),
]

# Greenhouse status banner (single line)
gh_banner = None
if GREENHOUSE_ENABLED:
    gh_banner = make_greenhouse_banner(x=FUTURE_BANNER_LEFT, y=57)

# EV status banners
ev_battery_banner = None
ev_charge_banner = None
if EV_ENABLED:
    ev_battery_banner = make_ev_banner(x=FUTURE_BANNER_LEFT, y=72)
    ev_charge_banner = make_ev_banner(x=FUTURE_BANNER_LEFT, y=87)

magtag.splash.append(today_banner)
for future_banner in future_banners:
    magtag.splash.append(future_banner)

if GREENHOUSE_ENABLED and gh_banner:
    magtag.splash.append(gh_banner)

if EV_ENABLED and ev_battery_banner and ev_charge_banner:
    magtag.splash.append(ev_battery_banner)
    magtag.splash.append(ev_charge_banner)

# Plug status banner
plug_banner = None
if GREENHOUSE_ENABLED:
    plug_banner = make_plug_banner(x=FUTURE_BANNER_LEFT, y=102)
    magtag.splash.append(plug_banner)

# ===========
#  M A I N
# ===========
voltage = magtag.peripherals.battery

print("Fetching forecast...")
try:
    resp_data = get_forecast()
    forecast_data = resp_data.json()
except (RuntimeError, OSError, KeyError) as error:
    print(f"Error getting forecast: {error}")
    # Sleep and try again later
    go_to_sleep_with_alarms()

if voltage > BATTERY_MINIMUM_VOLTAGE:

    print("Updating...")
    update_today(forecast_data)
    update_future(forecast_data)

    # Fetch and update greenhouse status
    if GREENHOUSE_ENABLED:
        print("Fetching greenhouse status...")
        try:
            gh_data = get_greenhouse_status()
            update_greenhouse_status(gh_banner, gh_data)
        except Exception as error:
            print(f"Greenhouse status error: {error}")
            update_greenhouse_status(gh_banner, None)

    # Fetch and update plug status
    if GREENHOUSE_ENABLED and plug_banner:
        try:
            plug_data = get_plug_status()
            update_plug_status(plug_banner, plug_data)
        except Exception as error:
            print(f"Plug status error: {error}")
            update_plug_status(plug_banner, None)

    # Fetch and update EV status
    if EV_ENABLED:
        print("Fetching EV status...")
        try:
            ev_data = get_ev_status()
            update_ev_status(ev_battery_banner, ev_charge_banner, ev_data)
        except Exception as error:
            print(f"EV status error: {error}")
            update_ev_status(ev_battery_banner, ev_charge_banner, None)

    print("Refreshing...")
    time.sleep(magtag.display.time_to_refresh + DISPLAY_REFRESH_DELAY)
    magtag.display.refresh()
    time.sleep(magtag.display.time_to_refresh + DISPLAY_REFRESH_DELAY)
else:
    # Battery too low for display update
    magtag.add_text(
        text_position=(10, (magtag.graphics.display.height // 2) - 1),
        text_scale=4,
    )

    magtag.set_text("LOW BATTERY!")

    button_colors = ((255, 0, 0), (255, 150, 0), (0, 255, 255), (180, 0, 255))

    print(f"Battery: {voltage} V")
    if voltage < BATTERY_CRITICAL_VOLTAGE:
        # Critical battery - brief flash then sleep immediately
        for _ in range(LED_FLASH_COUNT):
            magtag.peripherals.neopixel_disable = False
            magtag.peripherals.neopixels.fill(button_colors[0])
            time.sleep(LED_FLASH_DURATION)
            magtag.peripherals.neopixel_disable = True
            time.sleep(LED_FLASH_INTERVAL)

        print("Battery critical! Sleeping immediately...")
        go_to_sleep_with_alarms()
    else:
        # Low battery - show brief color cycle then continue to sleep
        magtag.peripherals.neopixel_disable = False
        magtag.peripherals.neopixels.fill(button_colors[0])
        time.sleep(0.25)
        magtag.peripherals.neopixels.fill(button_colors[1])
        time.sleep(0.25)
        magtag.peripherals.neopixels.fill(button_colors[2])
        time.sleep(0.25)
        magtag.peripherals.neopixels.fill(button_colors[3])
        time.sleep(0.25)
        magtag.peripherals.neopixel_disable = True

print("Sleeping...")
go_to_sleep_with_alarms()

# Entire code will run again after deep sleep cycle (similar to hitting the reset button)
