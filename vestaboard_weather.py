import datetime
import os
import requests

# ==============================================================================
# CONFIGURATION
# ==============================================================================

LATITUDE = 40.7128
LONGITUDE = -74.0060

# Choose layout: 1, 2, 3, or 4 (Option 4 has the blue rain flaps)
LAYOUT_STYLE = 4

# Set this to True to force the blue blocks right now for testing!
TEST_BLUE_BLOCKS = False

# ==============================================================================

VESTABOARD_API_KEY = os.environ.get("VESTABOARD_READ_WRITE_KEY")

# WMO codes that trigger the blue blocks (Drizzle, Rain, Snow, Showers, Storms)
PRECIP_CODES = {
    51,
    53,
    55,
    56,
    57,  # Drizzle
    61,
    63,
    65,
    66,
    67,  # Rain
    71,
    73,
    75,
    77,  # Snow
    80,
    81,
    82,
    85,
    86,  # Showers
    95,
    96,
    99,  # Thunderstorms
}

WEATHER_CODES = {
    0: "CLEAR SKY",
    1: "SUNNY SKIES",
    2: "PARTLY CLOUDY",
    3: "FULL OVERCAST",
    45: "FOGGY",
    48: "DENSE FOG",
    51: "LIGHT DRIZZLE",
    53: "DRIZZLE",
    55: "HEAVY DRIZZLE",
    61: "SLIGHT RAIN",
    63: "STEADY RAIN",
    65: "SEVERE RAIN",
    71: "SLIGHT SNOW",
    73: "STEADY SNOW",
    75: "SNOWSTORM",
    80: "SHOWERS",
    81: "HEAVY SHOWERS",
    82: "STORM SHOWERS",
    95: "THUNDERSTORMS",
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

    code = current["weather_code"]
    is_precip = (code in PRECIP_CODES) or TEST_BLUE_BLOCKS

    return {
        "temp": round(current["temperature_2m"]),
        "condition": WEATHER_CODES.get(code, "VARIABLE"),
        "high": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]),
        "rain": daily["precipitation_probability_max"][0],
        "is_precip": is_precip,
    }


def format_display(weather, style):
    now_str = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")

    # Keep rain string exactly 9 characters
    if weather["rain"] >= 100:
        rain_text = "RAIN:100%"
    else:
        rain_text = f"RAIN: {weather['rain']:>2}%"

    # Bottom row: add 2 blue flaps ({67}{67}) on each side if rain/snow is active
    if weather["is_precip"]:
        # 2 blue + 1 space + 9 chars + 1 space + 2 blue = 15 flaps
        bottom_row = f"{{67}}{{67}} {rain_text} {{67}}{{67}}"
    else:
        bottom_row = f"   {rain_text}   "

    if style == 1:
        return [
            weather["condition"].center(15),
            f"NOW  {weather['temp']}".center(15),
            f"H {weather['high']}   L {weather['low']}".center(15),
        ]
    elif style == 2:
        return [
            f"{weather['temp']}".center(15),
            f"H:{weather['high']}   L:{weather['low']}".center(15),
            weather["condition"].center(15),
        ]
    elif style == 3:
        return [
            weather["condition"].center(15),
            f"{weather['temp']}  H:{weather['high']} L:{weather['low']}".center(
                15
            ),
            now_str.center(15),
        ]
    else:
        # Option 4 (Default)
        return [
            weather["condition"].center(15),
            f"{weather['temp']}  H:{weather['high']} L:{weather['low']}".center(
                15
            ),
            bottom_row,
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
        f"Posted to Note (Precipitation: {weather['is_precip']}). Status: {res.status_code}"
    )


if __name__ == "__main__":
    send_to_vestaboard(get_weather())
