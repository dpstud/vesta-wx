import datetime
import os
import requests

LATITUDE = 40.7128
LONGITUDE = -74.0060
LAYOUT_STYLE = 4

VESTABOARD_API_KEY = os.environ.get("VESTABOARD_READ_WRITE_KEY")

# All condition names are tuned to odd lengths (7, 9, 11, 13)
# so they divide symmetrically across the Note's 15 columns
WEATHER_CODES = {
    0: "CLEAR SKY",  # 9 chars -> 3 spaces each side
    1: "SUNNY SKIES",  # 11 chars -> 2 spaces each side
    2: "PARTLY CLOUDY",  # 13 chars -> 1 space each side
    3: "FULL OVERCAST",  # 13 chars -> 1 space each side (or "VERY CLOUDY")
    45: "FOGGY",  # 5 chars -> 5 spaces each side
    48: "DENSE FOG",  # 9 chars -> 3 spaces each side
    51: "LIGHT DRIZZLE",  # 13 chars -> 1 space each side
    53: "DRIZZLE",  # 7 chars -> 4 spaces each side
    55: "HEAVY DRIZZLE",  # 13 chars -> 1 space each side
    61: "SLIGHT RAIN",  # 11 chars -> 2 spaces each side
    63: "STEADY RAIN",  # 11 chars -> 2 spaces each side
    65: "SEVERE RAIN",  # 11 chars -> 2 spaces each side
    71: "SLIGHT SNOW",  # 11 chars -> 2 spaces each side
    73: "STEADY SNOW",  # 11 chars -> 2 spaces each side
    75: "SNOWSTORM",  # 9 chars -> 3 spaces each side
    80: "SHOWERS",  # 7 chars -> 4 spaces each side
    81: "HEAVY SHOWERS",  # 13 chars -> 1 space each side
    82: "STORM SHOWERS",  # 13 chars -> 1 space each side
    95: "THUNDERSTORMS",  # 13 chars -> 1 space each side
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

    # Pads single-digit rain percentages so line is always 9 chars
    rain_str = f"RAIN: {weather['rain']:>2}%"

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
            rain_str.center(15),
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
    print(f"Posted status: {res.status_code}")


if __name__ == "__main__":
    send_to_vestaboard(get_weather())
