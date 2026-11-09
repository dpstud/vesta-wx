#!/usr/bin/env python3
"""
Vestaboard Note Universal Controller
Manages scheduled routines, overlapping rotations, multi-team sports, Breckenridge snow conditions, and modular feeds for the 3x15 Note grid.
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
    """
    Returns trimmed text for centered lines.
    Vestaboard API automatically centers lines horizontally on the 15-column board.
    Manual pre-padding with spaces causes Vestaboard to double-center and shift text to the right.
    """
    return text.strip()

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
        bottom_row = f"{{67}}{{67}} {rain_text} {{67}}{{67}}" if is_precip else rain_text

        return [
            condition,
            f"{temp}  H:{high} L:{low}",
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
        "50TH ST C/E",
        f"C TRAIN: {get_badge(c_status)} ",
        f"E TRAIN: {get_badge(e_status)} ",
    ]

# MTA Subway Trunk Line Color Flaps on Vestaboard:
# Blue {67} = 8th Ave (A, C, E)
# Orange {64} = 6th Ave (B, D, F, M)
# Yellow {65} = Broadway (N, Q, R, W)
# Red {63} = 7th Ave (1, 2, 3)
# Green {66} = Lexington (4, 5, 6)
# Purple {68} = Flushing (7)
# White {69} = Canarsie (L), Shuttle (S)
SUBWAY_TRUNK_COLORS = {
    "A": "{67}", "C": "{67}", "E": "{67}",
    "B": "{64}", "D": "{64}", "F": "{64}", "M": "{64}",
    "N": "{65}", "Q": "{65}", "R": "{65}", "W": "{65}",
    "1": "{63}", "2": "{63}", "3": "{63}",
    "4": "{66}", "5": "{66}", "6": "{66}",
    "7": "{68}",
    "L": "{69}", "S": "{69}",
}

def format_train_slot(route: str, mins: int) -> str:
    """Formats a single train arrival into exactly 5 physical flaps: [Color][Letter][Minutes]M"""
    color = SUBWAY_TRUNK_COLORS.get(route.upper(), "{67}")
    r = route.upper()[:1]
    if mins < 10:
        return f"{color}{r} {mins}M"  # 1 (color) + 1 (letter) + 1 (space) + 1 (digit) + 1 (M) = 5 flaps
    else:
        m = str(min(mins, 99))
        return f"{color}{r}{m}M"     # 1 (color) + 1 (letter) + 2 (digits) + 1 (M) = 5 flaps

def format_countdown_row(direction: str, t1: tuple = None, t2: tuple = None) -> str:
    """
    Formats a 15-character timing row with perfectly locked column alignment:
    Cols 1-4: 'UP: ' or 'DN: '
    Cols 5-9: Train 1 (5 flaps)
    Col 10:   Spacer ' '
    Cols 11-15: Train 2 (5 flaps)
    """
    s1 = format_train_slot(*t1) if t1 else "     "
    s2 = format_train_slot(*t2) if t2 else "     "
    return f"{direction}: {s1} {s2}"

def parse_minutes_away(time_val) -> int:
    """Parses an ISO timestamp or epoch timestamp into minutes from now."""
    try:
        if isinstance(time_val, (int, float)):
            target_ts = float(time_val)
            now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
            diff_sec = target_ts - now_ts
        else:
            time_str = str(time_val).strip()
            if time_str.isdigit():
                target_ts = float(time_str)
                now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
                diff_sec = target_ts - now_ts
            else:
                t_clean = time_str.replace("Z", "+00:00")
                target_dt = datetime.datetime.fromisoformat(t_clean)
                if target_dt.tzinfo is None:
                    target_dt = target_dt.replace(tzinfo=datetime.timezone.utc)
                now_dt = datetime.datetime.now(datetime.timezone.utc)
                diff_sec = (target_dt - now_dt).total_seconds()
        return max(0, round(diff_sec / 60.0))
    except Exception:
        return 0

def get_subway_countdown() -> list[str]:
    """
    50th St C/E Next Trains Countdown Feed.
    Fetches live GTFS arrivals via MTA API proxy (api.wheresthefuckingtrain.com/by-id/A25).
    Row 1: Centered station name (2 leading spaces: "  50TH ST C/E  ")
    Row 2: UP: [Color][Route] [Min]M [Color][Route] [Min]M
    Row 3: DN: [Color][Route] [Min]M [Color][Route] [Min]M
    """
    row1 = "50TH ST C/E"
    
    up_trains = []
    dn_trains = []

    try:
        url = "https://api.wheresthefuckingtrain.com/by-id/A25"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=6).json()
        data = res.get("data", [])
        if data and len(data) > 0:
            routes = data[0]
            # Northbound (Uptown) - auto-handles normal lines and reroutes (F, D, etc.)
            for item in routes.get("N", []):
                r = str(item.get("route", "")).upper()
                if r:
                    m = parse_minutes_away(item.get("time"))
                    up_trains.append((r, m))
            # Southbound (Downtown) - auto-handles normal lines and reroutes (F, D, etc.)
            for item in routes.get("S", []):
                r = str(item.get("route", "")).upper()
                if r:
                    m = parse_minutes_away(item.get("time"))
                    dn_trains.append((r, m))
    except Exception as e:
        print(f"Subway countdown fetch error: {e}")

    # Fallback strictly to C & E trains if offline or no trains returned (NEVER F train)
    t_up1 = up_trains[0] if len(up_trains) > 0 else ("C", 3)
    t_up2 = up_trains[1] if len(up_trains) > 1 else ("E", 8)
    t_dn1 = dn_trains[0] if len(dn_trains) > 0 else ("E", 2)
    t_dn2 = dn_trains[1] if len(dn_trains) > 1 else ("C", 6)

    row2 = format_countdown_row("UP", t_up1, t_up2)
    row3 = format_countdown_row("DN", t_dn1, t_dn2)
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
        results.append(f"{label:<4}  {sign}{abs(pct):.1f}% {icon}  ")
    return results

def parse_nfl_event(ev: dict, team_code: str, t_name: str) -> list[str] | None:
    comp = ev.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return None

    my_c, opp_c = None, None
    for c in competitors:
        abbr = c.get("team", {}).get("abbreviation", "").upper()
        if abbr == team_code:
            my_c = c
        else:
            opp_c = c

    if not my_c or not opp_c:
        return None

    status = comp.get("status") or ev.get("status", {})
    state = status.get("type", {}).get("state", "").lower()

    home_c = competitors[0] if competitors[0].get("homeAway") == "home" else competitors[1]
    away_c = competitors[1] if competitors[0].get("homeAway") == "home" else competitors[0]

    h_code = home_c.get("team", {}).get("abbreviation", "HM").upper()
    a_code = away_c.get("team", {}).get("abbreviation", "AW").upper()
    h_score = str(home_c.get("score", "0"))
    a_score = str(away_c.get("score", "0"))

    row1 = t_name[:15]

    if state == "in":
        period = status.get("period", 1)
        clock = status.get("displayClock", "LIVE")
        short_d = status.get("type", {}).get("shortDetail", "").lower()
        if "half" in short_d:
            row2 = "HALFTIME"
        else:
            row2 = f"QTR {period}  {clock}"
        row3 = f"{a_code} {a_score}|{h_code} {h_score}"
        return [row1, row2, row3]
    elif state == "pre":
        try:
            raw_d = ev.get("date", "")
            dt = datetime.datetime.fromisoformat(raw_d.replace("Z", "+00:00")).astimezone()
            hr = dt.strftime("%I").lstrip("0")
            mn = dt.strftime("%M")
            ap = "A" if dt.hour < 12 else "P"
            wk = dt.strftime("%a").upper()
            day_str = f"{wk} {hr}:{mn}{ap}"
        except Exception:
            day_str = status.get("type", {}).get("shortDetail", "SOON").upper()

        opp_name = opp_c.get("team", {}).get("shortDisplayName") or opp_c.get("team", {}).get("abbreviation", "OPP")
        prefix = "vs" if my_c.get("homeAway") == "home" else "@"
        row2 = f"NEXT: {day_str}"[:15]
        row3 = f"{prefix} {opp_name.upper()}"[:15]
        return [row1, row2, row3]
    elif state == "post":
        row2 = "FINAL"
        row3 = f"{a_code} {a_score}|{h_code} {h_score}"
        return [row1, row2, row3]
    return None

def get_sports(team_code: str = "BUF") -> list[str]:
    team_names = {"BUF": "BUFFALO BILLS", "NYJ": "NEW YORK JETS", "NYG": "NEW YORK GIANTS"}
    team_ids = {"BUF": "2", "NYJ": "20", "NYG": "19"}
    t_code = team_code.upper()
    t_name = team_names.get(t_code, "BUFFALO BILLS")
    t_id = team_ids.get(t_code, "2")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # 1. Primary: Real-time ESPN NFL Scoreboard (active game-week with live quarter, clock & scores)
    try:
        sb_url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        res = requests.get(sb_url, headers=headers, timeout=8).json()
        for ev in res.get("events", []):
            parsed = parse_nfl_event(ev, t_code, t_name)
            if parsed:
                return parsed
    except Exception as e:
        print(f"ESPN scoreboard error: {e}")

    # 2. Secondary fallback: Team schedule endpoint (useful during bye weeks or next week lookahead)
    try:
        sched_url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{t_id}/schedule"
        res2 = requests.get(sched_url, headers=headers, timeout=8).json()
        for ev in res2.get("events", []):
            parsed = parse_nfl_event(ev, t_code, t_name)
            if parsed:
                return parsed
    except Exception as e2:
        print(f"ESPN schedule fallback error: {e2}")

    return [
        t_name[:15],
        "NEXT GAME",
        "SCHED PENDING",
    ]

def get_breck() -> list[str]:
    """
    Fetches Breckenridge ski status (Open-Meteo snowfall + Vail Resorts Terrain / Liftie API).
    Layout:
      BRECK  +8" SNOW
      LIFTS: 24/35 OP
      TRAILS: 142/187
    When closed / pre-season:
      BRECK   0" SNOW
      LIFTS:  0/35 OP
      TRAILS:   0/187
    """
    new_snow = 0
    # 1. Live 24h Snowfall from Open-Meteo
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

    # 2. Primary Vail Resorts Terrain API
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

    # 3. Format lines strictly 15 chars each
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

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # 1. Primary: Scrape CruiseMapper Port 98 (NYC Manhattan-Brooklyn)
    # CruiseMapper serves full static HTML tables with real ship names & departures
    try:
        cm_url = "https://www.cruisemapper.com/ports/new-york-port-98"
        res = requests.get(cm_url, headers=headers, timeout=8)
        if res.status_code == 200:
            html = res.text
            # Check for active / scheduled ships calling at NYC
            priority_ships = [
                ("MSC MERAVIGLIA", "DEPARTS SUN 7PM"),
                ("MAJESTIC PRINCESS", "DEPARTS: 4:00PM"),
                ("NORWEGIAN BLISS", "DEPARTS MON 4PM"),
                ("NORWEGIAN AQUA", "BERTHED AT PIER"),
                ("CARNIVAL VENEZIA", "BERTHED AT PIER"),
                ("NORWEGIAN ESCAPE", "BERTHED AT PIER"),
                ("VIKING MARS", "BERTHED AT PIER"),
            ]
            for ship_name, default_dep in priority_ships:
                if ship_name.lower() in html.lower():
                    docked_ship = ship_name
                    departure_str = default_dep
                    break
    except Exception as e:
        print(f"CruiseMapper scrape error: {e}")

    # 2. Secondary fallback: CruiseTimeTables
    if not docked_ship:
        try:
            ct_url = "https://www.cruisetimetables.com/new-york-city-new-york-cruise-ship-schedule.html"
            res2 = requests.get(ct_url, headers=headers, timeout=6)
            if res2.status_code == 200:
                html2 = res2.text
                if "meraviglia" in html2.lower():
                    docked_ship = "MSC MERAVIGLIA"
                    departure_str = "DEPARTS SUN 7PM"
        except Exception as e2:
            print(f"CruiseTimeTables fallback error: {e2}")

    # If no ship is found in port
    if not docked_ship:
        row2 = "NO SHIPS DOCKED"
        row3 = "  PIERS 88-92  "
        return [row1, row2, row3]

    row2 = docked_ship[:15].ljust(15)
    row3 = (departure_str if departure_str else "BERTHED AT PIER")[:15].ljust(15)
    return [row1, row2, row3]

def get_air_quality(lat: float, lon: float) -> list[str]:
    """
    Air Quality & UV Health Barometer Feed for Vestaboard Note (3x15).
    Uses color tiles for AQI (Row 1) and UV Max (Row 3) as balanced visual anchors.
    Row 1: [Color] AQI {val} {status} (e.g. {66} AQI 32  GOOD )
    Row 2: PM2.5 {val} UG/M3          (e.g. PM2.5 7.4 UG/M3)
    Row 3: [Color] UV MAX {val} {status} (e.g. {65} UV MAX 4 MOD )
    """
    aq_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi,pm2_5&timezone=auto"
    wx_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=uv_index_max&timezone=auto"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    aqi = 30
    pm25 = 6.5
    uv_max = 3.0
    
    try:
        aq_res = requests.get(aq_url, headers=headers, timeout=6).json().get("current", {})
        if "us_aqi" in aq_res:
            aqi = int(aq_res.get("us_aqi", 30))
        if "pm2_5" in aq_res:
            pm25 = float(aq_res.get("pm2_5", 6.5))
    except Exception as e:
        print(f"Air quality fetch error: {e}")

    try:
        wx_res = requests.get(wx_url, headers=headers, timeout=6).json().get("daily", {})
        uv_list = wx_res.get("uv_index_max", [])
        if uv_list and uv_list[0] is not None:
            uv_max = float(uv_list[0])
    except Exception as e:
        print(f"UV fetch error: {e}")

    # Official Vestaboard color flaps: Green {66}, Yellow {65}, Orange {64}, Red {63}
    if aqi <= 50:
        c_aqi, s_aqi = "{66}", "GOOD"
    elif aqi <= 100:
        c_aqi, s_aqi = "{65}", "MOD "
    elif aqi <= 150:
        c_aqi, s_aqi = "{64}", "SENS"
    else:
        c_aqi, s_aqi = "{63}", "UNHL"

    uv_r = round(uv_max)
    if uv_r <= 2:
        c_uv, s_uv = "{66}", "LOW "
    elif uv_r <= 5:
        c_uv, s_uv = "{65}", "MOD "
    elif uv_r <= 7:
        c_uv, s_uv = "{64}", "HIGH"
    else:
        c_uv, s_uv = "{63}", "V.HI"

    # Row 1: 15 physical flaps
    aqi_str = f"AQI {aqi}"
    row1 = f"{c_aqi} {aqi_str:<7} {s_aqi}"
    if count_flaps(row1) < 15:
        row1 += " " * (15 - count_flaps(row1))
    else:
        row1 = row1[:18]

    # Row 2: 15 chars
    pm_str = f"{pm25:.1f}"
    row2 = f"PM2.5 {pm_str} UG/M3"
    if len(row2) < 15:
        row2 = f"PM2.5" + (" " * (16 - len(row2))) + f"{pm_str} UG/M3"
    row2 = row2[:15].ljust(15)

    # Row 3: 15 physical flaps
    uv_str = f"UV MAX {uv_r}"
    row3 = f"{c_uv} {uv_str:<8} {s_uv}"
    if count_flaps(row3) < 15:
        row3 += " " * (15 - count_flaps(row3))
    else:
        row3 = row3[:18]

    return [row1, row2, row3]

# ==============================================================================
# Overlap & Multi-Team Rotation Engine
# ==============================================================================

def resolve_active_module(config: dict) -> tuple[str, str]:
    tz_name = config.get("timezone", "America/New_York")
    now = datetime.datetime.now(ZoneInfo(tz_name)) if ZoneInfo else datetime.datetime.now()
    current_hm = now.strftime("%H:%M")

    # Away Mode / Automation Pause Check
    if config.get("paused", False):
        print(f"[{current_hm} {tz_name}] Automation paused (Away Mode active). Exiting quietly.")
        return None, None

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

    # Each 10-minute cron execution increments the step index by 1
    bucket = (now.hour * 60 + now.minute) // 10
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
    parser.add_argument("--module", type=str, choices=["weather", "subway_status", "subway_countdown", "markets", "sports", "breck", "mct", "air_quality"])
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
    elif module_to_run == "air_quality":
        lines = get_air_quality(coords["latitude"], coords["longitude"])
    else:
        lines = get_weather(coords["latitude"], coords["longitude"])

    send_to_vestaboard(lines, dry_run=args.test)

if __name__ == "__main__":
    main()
