# SPDX-FileCopyrightText: 2024 Carter Nelson for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
User configuration settings for MagTag Weather Display
"""

# Location settings
LAT = 42.5236  # latitude
LON = -71.1030  # longitude
TMZ = "America/New_York"  # https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
CITY = "Boston"  # optional city name for display

# Display settings
METRIC = False  # set to True for metric units

# Sleep/update settings
SLEEP_TIME = 60 * 60  # Sleep time in seconds (1 hour)

# Battery voltage thresholds
BATTERY_CRITICAL_VOLTAGE = 3.2  # Below this, show low battery warning
BATTERY_MINIMUM_VOLTAGE = 3.0  # Below this, skip display update

# EV Status settings
EV_ENABLED = True  # Set to False to disable EV status display

# Greenhouse settings
GREENHOUSE_ENABLED = True  # Set to False to disable greenhouse status display
