import datetime
import os
import requests

# Set your city's latitude and longitude
LATITUDE = 40.7128
LONGITUDE = -74.0060

VESTABOARD_API_KEY = os.environ.get("VESTABOARD_READ_WRITE_KEY")

WEATHER_CODES = {
    0: "CLEAR SKY",
    1: "MAINLY CLEAR",
    2: "PARTLY CLOUDY",
    3: "OVERCAST",
    45: "FOGGY",
    48: "DEPOSITING FOG",
    51: "LIGHT DRIZZLE",
    53: "MODERATE DRIZZLE",
    55: "DENSE DRIZZLE",
    61: "SLIGHT RAIN",
    63: "MODERATE RAIN",
    65: "HEAVY RAIN",
    71: "SLIGHT SNOW",
    73: "MODERATE SNOW",
    75: "HEAVY SNOW",
    80: "RAIN SHOWERS",
    81: "HEAVY SHOWERS",
    82: "VIOLENT SHOWERS",
    95: "THUNDERSTORM",
}


def get_live_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={LATITUDE}&longitude={LONGITUDE}&"
        f"current=temperature_2m,apparent_temperature,weather_code,relative_humidity_2m,wind_speed_10m&"
        f"temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto"
    )
    res = requests.get(url, timeout=10).json()
    current = res["current"]
    return {
        "temp": round(current["temperature_2m"]),
        "feels_like": round(current["apparent_temperature"]),
        "condition": WEATHER_CODES.get(current["weather_code"], "VARIABLE"),
        "wind": round(current["wind_speed_10m"]),
        "humidity": current["relative_humidity_2m"],
    }


def send_to_vestaboard(weather):
    now_str = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")

    # 6 lines, 22 characters per line
    lines = [
        "CURRENT WEATHER".center(22),
        weather["condition"].center(22),
        f"TEMP: {weather['temp']}F (FEEL {weather['feels_like']}F)".center(22),
        f"WIND: {weather['wind']} MPH | {weather['humidity']}% HUM".center(22),
        "".center(22),
        f"UPDATED: {now_str}".center(22),
    ]

    message = "\n".join(lines)

    res = requests.post(
        "https://rw.vestaboard.com/",
        headers={"X-Vestaboard-Read-Write-Key": VESTABOARD_API_KEY},
        json={"text": message},
        timeout=10,
    )
    print(f"[{now_str}] Vestaboard response: {res.status_code}")


if __name__ == "__main__":
    send_to_vestaboard(get_live_weather())
