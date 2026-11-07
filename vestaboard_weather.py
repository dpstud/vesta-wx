import datetime
import os
import requests

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Set your city's latitude and longitude
LATITUDE = 40.7128
LONGITUDE = -74.0060

# Choose your layout (1, 2, 3, or 4):
#
#   OPTION 1: The Classic Glance
#     +---------------+
#     | PARTLY CLOUDY |
#     |    NOW  68    |
#     |  H 74   L 52  |
#     +---------------+
#
#   OPTION 2: Numbers First
#     +---------------+
#     |      68       |
#     |  H:74   L:52  |
#     | PARTLY CLOUDY |
#     +---------------+
#
#   OPTION 3: With Live Timestamp
#     +---------------+
#     | PARTLY CLOUDY |
#     | 68  H:74 L:52 |
#     |   10:30 PM    |
#     +---------------+
#
#   OPTION 4: With Rain Chance (Default)
#     +---------------+
#     | PARTLY CLOUDY |
#     | 68  H:74 L:52 |
#     |   RAIN: 20%   |
#     +---------------+
#
LAYOUT_STYLE = 4

# ==============================================================================

VESTABOARD_API_KEY = os.environ.get("VESTABOARD_READ_WRITE_KEY")

# Shortened names guaranteed to fit the Note's 15-character width
WEATHER_CODES = {
    0: "CLEAR SKY",
    1: "MAINLY CLEAR",
    2: "PARTLY CLOUDY",
    3: "OVERCAST",
    45: "FOGGY",
    48: "FOG",
    51: "LIGHT DRIZZLE",
    53: "DRIZZLE",
    55: "HEAVY DRIZZLE",
    61: "LIGHT RAIN",
    63: "RAIN",
    65: "HEAVY RAIN",
    71: "LIGHT SNOW",
    73: "SNOW",
    75: "HEAVY SNOW",
    80: "SHOWERS",
    81: "HEAVY SHOWERS",
    82: "STORM SHOWERS",
    95: "THUNDERSTORM",
}


def get_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={LATITUDE}&longitude={LONGITUDE}&"
        f"current=temperature_2m,weather_code&"
        f"daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&"
        f"temperature_unit=fahrenheit&timezone=auto"
    )
    res = requests.get(url, timeout=10).json()
    current = res["current"]
    daily = res["daily"]

    return {
        "temp": round(current["temperature_2m"]),
        "condition": WEATHER_CODES.get(current["weather_code"], "VARIABLE"),
        "high": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]),
        "rain": daily["precipitation_probability_max"][0],
    }


def format_display(weather, style):
    now_str = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")

    if style == 1:
        # The Classic Glance
        return [
            weather["condition"].center(15),
            f"NOW  {weather['temp']}".center(15),
            f"H {weather['high']}   L {weather['low']}".center(15),
        ]
    elif style == 2:
        # Numbers First
        return [
            f"{weather['temp']}".center(15),
            f"H:{weather['high']}   L:{weather['low']}".center(15),
            weather["condition"].center(15),
        ]
    elif style == 3:
        # With Timestamp
        return [
            weather["condition"].center(15),
            f"{weather['temp']}  H:{weather['high']} L:{weather['low']}".center(
                15
            ),
            now_str.center(15),
        ]
    else:
        # Option 4 (Default): With Rain Chance
        return [
            weather["condition"].center(15),
            f"{weather['temp']}  H:{weather['high']} L:{weather['low']}".center(
                15
            ),
            f"RAIN: {weather['rain']}%".center(15),
        ]


def send_to_vestaboard(weather):
    lines = format_display(weather, LAYOUT_STYLE)
    message = "\n".join(lines)

    res = requests.post(
        "https://rw.vestaboard.com/",
        headers={"X-Vestaboard-Read-Write-Key": VESTABOARD_API_KEY},
        json={"text": message},
        timeout=10,
    )
    print(
        f"Posted Option {LAYOUT_STYLE} to Note. Vestaboard status: {res.status_code}"
    )


if __name__ == "__main__":
    send_to_vestaboard(get_weather())
