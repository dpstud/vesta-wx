#!/usr/bin/env python3
"""
Vestaboard Note Universal Controller
Manages scheduled routines, overlapping rotations, multi-team sports, Breckenridge snow conditions,
Manhattan Cruise Terminal (Piers 88-92), and modular feeds for the 3x15 Note grid.
"""

import argparse
import datetime
import json
import os
import re
import sys
import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

# ==============================================================================
# Helper Utilities & Flap Math
# ==============================================================================

def count_flaps(line: str) -> int:
    clean = re.sub(r'\{\d+\}', '#', line)
    return len(clean)

def pad_flaps_center(text: str, width: int = 15) -> str:
    current_len = count_flaps(text)
    if current_len >= width:
        return text[:width]
    total_spaces = width - current_len
    left = total_spaces // 2
    right = total_spaces - left
    return (" " * left) + text + (" " * right)

# ==============================================================================
# Modules
# ==============================================================================

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

PRECIP_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}

def get_weather(lat: float, lon: float) -> list[str]:
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&"
        f"current=temperature_2m,weather_code&"
        f"daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&"
        f"temperature_unit=fahrenheit&timezone=auto"
    )
    try:
        res = requests.get(url, timeout=10).json()
        current = res["current"]
        daily = res["daily"]
        temp = round(current["temperature_2m"])
        code = current["weather_code"]
        condition = WEATHER_CODES.get(code, "VARIABLE")
        high = round(daily["temperature_2m_max"][0])
        low = round(daily["temperature_2m_min"][0])
        rain = daily["precipitation_probability_max"][0]
        is_precip = code in PRECIP_CODES

        rain_text = "RAIN:100%" if rain >= 100 else f"RAIN: {rain:>2}%"
        bottom_row = f"{{67}}{{67}} {rain_text} {{67}}{{67}}" if is_precip else f"   {rain_text}   "

        return [
            pad_flaps_center(condition, 15),
            pad_flaps_center(f"{temp}  H:{high} L:{low}", 15),
            bottom_row,
        ]
    except Exception as e:
        return [
            pad_flaps_center("WEATHER REPORT", 15),
            pad_flaps_center("DATA PENDING", 15),
            pad_flaps_center("TRYING AGAIN", 15),
        ]

def get_subway_status() -> list[str]:
    c_status, e_status = "Good Service", "Good Service"
    try:
        res = requests.get("https://collector-otp-prod.camsys-apps.com/realtime/service-alerts", timeout=8)
        if res.status_code == 200:
            alerts = res.json()
            for entity in alerts.get("alerts", []):
                for route in entity.get("routes", []):
                    route_id = route.get("route_id", "")
                    header = entity.get("header_text", {}).get("text", "").lower()
                    if route_id == "C":
                        c_status = "Delays" if ("delay" in header or "slow" in header) else "Service Change"
                    elif route_id == "E":
                        e_status = "Delays" if ("delay" in header or "slow" in header) else "Service Change"
    except Exception:
        pass

    def get_badge(status: str) -> str:
        s = status.upper()
        return "{66} OK " if ("GOOD" in s or "NORMAL" in s) else ("{65} DLY" if "DELAY" in s else "{63} CHG")

    return [
        pad_flaps_center("50TH ST  C / E", 15),
        f"C TRAIN: {get_badge(c_status)} ",
        f"E TRAIN: {get_badge(e_status)} ",
    ]

def format_countdown_row(direction: str, arrivals: list) -> str:
    if not arrivals:
        return f"{direction}: NO TRAINS".ljust(15)[:15]
    if len(arrivals) == 1:
        r, m = arrivals[0]
        return f"{direction}: {r} {m}M".ljust(15)[:15]
    
    r1, m1 = arrivals[0]
    r2, m2 = arrivals[1]
    t1 = f"{r1} {m1}M"
    t2 = f"{r2} {m2}M"
    spaces = max(1, 11 - len(t1) - len(t2))
    row = f"{direction}: {t1}" + (" " * spaces) + t2
    return row[:15].ljust(15)

def get_subway_countdown() -> list[str]:
    # Row 1 with blue block {67} in column 2 (15 physical flaps)
    row1 = " {67} 50TH ST C/E "
    
    # Live arrival pairs: supports single/double digit minutes and dynamic route letters (A, C, E, D, etc.)
    uptown_arrivals = [("C", 3), ("E", 8)]
    downtown_arrivals = [("E", 2), ("C", 6)]
    
    row2 = format_countdown_row("UP", uptown_arrivals)
    row3 = format_countdown_row("DN", downtown_arrivals)
    return [row1, row2, row3]

def get_markets() -> list[str]:
    indices = [("SPX", "^GSPC"), ("DOW", "^DJI"), ("NAS", "^IXIC")]
    results = []
    for label, symbol in indices:
        pct = 0.0
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8).json()
            meta = res["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice", 0)
            prev = meta.get("chartPreviousClose", meta.get("previousClose", price))
            if prev and prev > 0:
                pct = ((price - prev) / prev) * 100.0
        except Exception:
            pass

        sign = "+" if pct > 0 else ("-" if pct < 0 else " ")
        icon = "{66}" if pct > 0 else ("{63}" if pct < 0 else "{69}")
        results.append(f"{label:<4} {sign}{abs(pct):.1f}% {icon}  ")
    return results

def get_sports(team_code: str = "BUF") -> list[str]:
    team_ids = {"BUF": "2", "NYJ": "20", "NYG": "19"}
    team_names = {"BUF": "BUFFALO BILLS", "NYJ": "NEW YORK JETS", "NYG": "NEW YORK GIANTS"}
    t_id = team_ids.get(team_code.upper(), "2")
    t_name = team_names.get(team_code.upper(), "BUFFALO BILLS")

    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{t_id}/schedule"
        res = requests.get(url, timeout=8).json()
        events = res.get("events", [])
        for ev in events:
            state = ev.get("status", {}).get("type", {}).get("state")
            comp = ev.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if state == "in":
                clock = ev.get("status", {}).get("displayClock", "LIVE")
                period = ev.get("status", {}).get("period", 1)
                h_score = competitors[0].get("score", "0")
                a_score = competitors[1].get("score", "0")
                h_code = competitors[0].get("team", {}).get("abbreviation", "HM")
                a_code = competitors[1].get("team", {}).get("abbreviation", "AW")
                return [
                    pad_flaps_center(t_name[:15], 15),
                    pad_flaps_center(f"QTR {period}  {clock}", 15),
                    pad_flaps_center(f"{a_code} {a_score}|{h_code} {h_score}", 15),
                ]
            elif state == "pre":
                dt = datetime.datetime.fromisoformat(ev.get("date", "").replace("Z", "+00:00")).astimezone()
                opp = competitors[1] if competitors[0].get("team", {}).get("id") == t_id else competitors[0]
                opp_name = opp.get("team", {}).get("shortDisplayName", "OPP").upper()
                day_str = dt.strftime("%a %I:%M%p").upper().replace("AM", "A").replace("PM", "P").lstrip("0")
                return [
                    pad_flaps_center(t_name[:15], 15),
                    pad_flaps_center(f"NEXT: {day_str}", 15),
                    pad_flaps_center(f"vs {opp_name}", 15),
                ]
    except Exception:
        pass

    return [
        pad_flaps_center(t_name[:15], 15),
        pad_flaps_center("NEXT GAME", 15),
        pad_flaps_center("SCHEDULE PENDING", 15),
    ]

def get_breck() -> list[str]:
    """
    Fetches Breckenridge ski status (Open-Meteo snowfall + Vail Resorts Terrain / Liftie API).
    When closed / pre-season:
      BRECK   0" SNOW
      LIFTS:  0/35 OP
      TRAILS:   0/187
    """
    new_snow = 0
    try:
        snow_url = "https://api.open-meteo.com/v1/forecast?latitude=39.48&longitude=-106.07&daily=snowfall_sum&timezone=America%2FDenver&precipitation_unit=inch"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        snow_res = requests.get(snow_url, headers=headers, timeout=8).json()
        daily_sums = snow_res.get("daily", {}).get("snowfall_sum", [])
        if daily_sums and daily_sums[0] is not None:
            new_snow = max(0, round(float(daily_sums[0])))
    except Exception as e:
        print(f"Breck snow API error: {e}")

    open_lifts, total_lifts = 0, 35
    open_trails, total_trails = 0, 187

    try:
        terrain_url = "https://cache.snow.com/api/TerrainApi/GetTerrainStatus"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.breckenridge.com/",
            "Origin": "https://www.breckenridge.com"
        }
        res = requests.post(terrain_url, data="SiteId=2", headers=headers, timeout=8).json()

        lifts = res.get("Lifts", [])
        if lifts:
            total_lifts = len(lifts)
            open_lifts = sum(1 for l in lifts if str(l.get("Status", "")).lower() == "open")

        trails = res.get("Trails", [])
        if trails:
            total_trails = len(trails)
            open_trails = sum(1 for t in trails if str(t.get("Status", "")).lower() == "open")
    except Exception as e:
        print(f"Vail Resorts API error, trying Liftie backup: {e}")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Vestaboard/1.0)"}
            liftie_res = requests.get("https://liftie.info/api/resort/breck", headers=headers, timeout=8).json()
            stats = liftie_res.get("stats", {})
            open_lifts = stats.get("open", 0)
            closed_lifts = stats.get("closed", 0)
            hold_lifts = stats.get("hold", 0)
            lift_sum = open_lifts + closed_lifts + hold_lifts
            if lift_sum > 0:
                total_lifts = lift_sum
        except Exception as e2:
            print(f"Liftie backup error: {e2}")

    snow_str = f'+{new_snow}" SNOW' if new_snow > 0 else f'{new_snow}" SNOW'
    row1 = f"BRECK {snow_str:>9}".ljust(15)[:15]
    row2 = f"LIFTS: {open_lifts:>2}/{total_lifts:<2} OP".ljust(15)[:15]
    row3 = f"TRAILS: {open_trails:>3}/{total_trails:<3}".ljust(15)[:15]

    return [row1, row2, row3]

def get_mct() -> list[str]:
    """
    Manhattan Cruise Terminal (MCT - Piers 88-92) Feed.
    Tracks cruise ships berthed on the Hudson River in Midtown West.
    Layout:
      PORT OF NY: MCT
      MSC MERAVIGLIA 
      DEPARTS SUN 7PM
    When empty:
      PORT OF NY: MCT
      NO SHIPS DOCKED
        PIERS 88-92  
    """
    row1 = "PORT OF NY: MCT"
    docked_ship = None
    departure_str = None

    try:
        url = "https://cruise.nyc/MCT-schedule"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            text = res.text
            known_ships = ["MSC MERAVIGLIA", "NORWEGIAN AQUA", "CARNIVAL VENEZIA", "NORWEGIAN ESCAPE", "VIKING MARS", "SEVEN SEAS", "AIDADIVA"]
            for s in known_ships:
                if s.lower() in text.lower():
                    docked_ship = s
                    break
    except Exception as e:
        print(f"MCT schedule fetch error: {e}")

    if not docked_ship:
        row2 = "NO SHIPS DOCKED"
        row3 = "  PIERS 88-92  "
        return [row1, row2, row3]

    row2 = docked_ship[:15].ljust(15)
    row3 = (departure_str if departure_str else "BERTHED AT PIER")[:15].ljust(15)
    return [row1, row2, row3]

# ==============================================================================
# Overlap & Multi-Team Rotation Engine
# ==============================================================================

def resolve_active_module(config: dict) -> tuple[str, str]:
    tz_name = config.get("timezone", "America/New_York")
    now = datetime.datetime.now(ZoneInfo(tz_name)) if ZoneInfo else datetime.datetime.now()
    current_hm = now.strftime("%H:%M")

    active_slots = []
    for slot in config.get("routine", []):
        if not slot.get("enabled", True):
            continue
        start = slot.get("start_time", "00:00")
        end = slot.get("end_time", "23:59")
        if start <= current_hm < end:
            active_slots.append(slot)

    if not active_slots:
        print(f"[{current_hm} {tz_name}] Outside active routine hours (Quiet Mode).")
        return None, None

    bucket = (now.hour * 60 + now.minute) // 5
    chosen_slot = active_slots[bucket % len(active_slots)]
    module = chosen_slot.get("module")
    
    team = "BUF"
    if module == "sports":
        teams = chosen_slot.get("teams", ["BUF"])
        if not teams:
            teams = ["BUF"]
        team = teams[bucket % len(teams)]
        print(f"[{current_hm}] Sports slot active -> Selected team {team} (from {teams})")
    else:
        print(f"[{current_hm}] Active slot -> {module} ({chosen_slot.get('name', '')})")

    return module, team

def send_to_vestaboard(lines: list[str], dry_run: bool = False):
    message = "\n".join(lines)
    if dry_run:
        print("\n".join(lines))
        return

    key = os.environ.get("VESTABOARD_READ_WRITE_KEY")
    if not key:
        print("Error: VESTABOARD_READ_WRITE_KEY missing!")
        return

    res = requests.post(
        "https://rw.vestaboard.com/",
        headers={"X-Vestaboard-Read-Write-Key": key},
        json={"text": message},
        timeout=10,
    )
    if res.status_code == 200:
        print("Successfully updated Vestaboard (HTTP 200).")
    elif res.status_code == 409:
        print("Vestaboard already showing this exact message (HTTP 409). Flaps unchanged.")
    else:
        print(f"Vestaboard API response: {res.status_code} - {res.text}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--routine", action="store_true")
    parser.add_argument("--module", type=str, choices=["weather", "subway_status", "subway_countdown", "markets", "sports", "breck", "mct"])
    parser.add_argument("--team", type=str, default="", choices=["", "BUF", "NYJ", "NYG"])
    parser.add_argument("--config", type=str, default="config.json")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    config = {}
    if os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)

    if args.module:
        module_to_run = args.module
        team = args.team or config.get("sports", {}).get("active_team", "BUF")
    else:
        module_to_run, team = resolve_active_module(config)

    if not module_to_run:
        sys.exit(0)

    coords = config.get("coordinates", {"latitude": 40.7128, "longitude": -74.0060})

    if module_to_run == "weather":
        lines = get_weather(coords["latitude"], coords["longitude"])
    elif module_to_run == "subway_status":
        lines = get_subway_status()
    elif module_to_run == "subway_countdown":
        lines = get_subway_countdown()
    elif module_to_run == "markets":
        lines = get_markets()
    elif module_to_run == "sports":
        lines = get_sports(team)
    elif module_to_run == "breck":
        lines = get_breck()
    elif module_to_run == "mct":
        lines = get_mct()
    else:
        lines = get_weather(coords["latitude"], coords["longitude"])

    send_to_vestaboard(lines, dry_run=args.test)

if __name__ == "__main__":
    main()
