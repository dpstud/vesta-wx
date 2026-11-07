#!/usr/bin/env python3
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
  return (' ' * left) + text + (' ' * right)


WEATHER_CODES = {
    0: 'CLEAR SKY',
    1: 'SUNNY SKIES',
    2: 'PARTLY CLOUDY',
    3: 'FULL OVERCAST',
    45: 'FOGGY',
    48: 'DENSE FOG',
    51: 'LIGHT DRIZZLE',
    53: 'DRIZZLE',
    55: 'HEAVY DRIZZLE',
    61: 'SLIGHT RAIN',
    63: 'STEADY RAIN',
    65: 'SEVERE RAIN',
    71: 'SLIGHT SNOW',
    73: 'STEADY SNOW',
    75: 'SNOWSTORM',
    80: 'SHOWERS',
    81: 'HEAVY SHOWERS',
    82: 'STORM SHOWERS',
    95: 'THUNDERSTORMS',
}

PRECIP_CODES = {
    51,
    53,
    55,
    56,
    57,
    61,
    63,
    65,
    66,
    67,
    71,
    73,
    75,
    77,
    80,
    81,
    82,
    85,
    86,
    95,
    96,
    99,
}


def get_weather(lat: float, lon: float) -> list[str]:
  url = (
      f'https://api.open-meteo.com/v1/forecast?'
      f'latitude={lat}&longitude={lon}&'
      f'current=temperature_2m,weather_code&'
      f'daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&'
      f'temperature_unit=fahrenheit&timezone=auto'
  )
  try:
    res = requests.get(url, timeout=10).json()
    current = res['current']
    daily = res['daily']
    temp = round(current['temperature_2m'])
    code = current['weather_code']
    condition = WEATHER_CODES.get(code, 'VARIABLE')
    high = round(daily['temperature_2m_max'][0])
    low = round(daily['temperature_2m_min'][0])
    rain = daily['precipitation_probability_max'][0]
    is_precip = code in PRECIP_CODES

    rain_text = 'RAIN:100%' if rain >= 100 else f'RAIN: {rain:>2}%'
    bottom_row = (
        f'{{67}}{{67}} {rain_text} {{67}}{{67}}'
        if is_precip
        else f'   {rain_text}   '
    )

    return [
        pad_flaps_center(condition, 15),
        pad_flaps_center(f'{temp}  H:{high} L:{low}', 15),
        bottom_row,
    ]
  except Exception:
    return [
        pad_flaps_center('WEATHER REPORT', 15),
        pad_flaps_center('DATA PENDING', 15),
        pad_flaps_center('TRYING AGAIN', 15),
    ]


def get_subway_status() -> list[str]:
  c_status, e_status = 'Good Service', 'Good Service'
  try:
    res = requests.get(
        'https://collector-otp-prod.camsys-apps.com/realtime/service-alerts',
        timeout=8,
    )
    if res.status_code == 200:
      alerts = res.json()
      for entity in alerts.get('alerts', []):
        for route in entity.get('routes', []):
          route_id = route.get('route_id', '')
          header = entity.get('header_text', {}).get('text', '').lower()
          if route_id == 'C':
            c_status = (
                'Delays'
                if ('delay' in header or 'slow' in header)
                else 'Service Change'
            )
          elif route_id == 'E':
            e_status = (
                'Delays'
                if ('delay' in header or 'slow' in header)
                else 'Service Change'
            )
  except Exception:
    pass

  def get_badge(status: str) -> str:
    s = status.upper()
    return (
        '{66} OK '
        if ('GOOD' in s or 'NORMAL' in s)
        else ('{65} DLY' if 'DELAY' in s else '{63} CHG')
    )

  return [
      pad_flaps_center('50TH ST  C / E', 15),
      f'C TRAIN: {get_badge(c_status)} ',
      f'E TRAIN: {get_badge(e_status)} ',
  ]


def get_subway_countdown() -> list[str]:
  uptown = ['C 3M', 'E 8M']
  downtown = ['E 2M', 'C 6M']
  up_str = f'UP: {uptown[0]:<4} {uptown[1]:<4}'
  dn_str = f'DN: {downtown[0]:<4} {downtown[1]:<4}'
  return [
      pad_flaps_center('50TH ST C/E', 15),
      pad_flaps_center(up_str.strip(), 15),
      pad_flaps_center(dn_str.strip(), 15),
  ]


def get_markets() -> list[str]:
  indices = [('SPX', '^GSPC'), ('DOW', '^DJI'), ('NAS', '^IXIC')]
  results = []
  for label, symbol in indices:
    pct = 0.0
    try:
      url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d'
      res = requests.get(
          url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8
      ).json()
      meta = res['chart']['result'][0]['meta']
      price = meta.get('regularMarketPrice', 0)
      prev = meta.get('chartPreviousClose', meta.get('previousClose', price))
      if prev and prev > 0:
        pct = ((price - prev) / prev) * 100.0
    except Exception:
      pass

    sign = '+' if pct > 0 else ('-' if pct < 0 else ' ')
    icon = '{66}' if pct > 0 else ('{63}' if pct < 0 else '{69}')
    results.append(f'{label:<4} {sign}{abs(pct):.1f}% {icon}  ')
  return results


def get_sports(team_code: str = 'BUF') -> list[str]:
  team_ids = {'BUF': '2', 'NYJ': '20', 'NYG': '19'}
  team_names = {
      'BUF': 'BUFFALO BILLS',
      'NYJ': 'NEW YORK JETS',
      'NYG': 'NEW YORK GIANTS',
  }
  t_id = team_ids.get(team_code.upper(), '2')
  t_name = team_names.get(team_code.upper(), 'BUFFALO BILLS')

  try:
    url = f'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{t_id}/schedule'
    res = requests.get(url, timeout=8).json()
    events = res.get('events', [])
    for ev in events:
      state = ev.get('status', {}).get('type', {}).get('state')
      comp = ev.get('competitions', [{}])[0]
      competitors = comp.get('competitors', [])
      if state == 'in':
        clock = ev.get('status', {}).get('displayClock', 'LIVE')
        period = ev.get('status', {}).get('period', 1)
        h_score = competitors[0].get('score', '0')
        a_score = competitors[1].get('score', '0')
        h_code = competitors[0].get('team', {}).get('abbreviation', 'HM')
        a_code = competitors[1].get('team', {}).get('abbreviation', 'AW')
        return [
            pad_flaps_center(t_name[:15], 15),
            pad_flaps_center(f'QTR {period}  {clock}', 15),
            pad_flaps_center(f'{a_code} {a_score}|{h_code} {h_score}', 15),
        ]
      elif state == 'pre':
        dt = datetime.datetime.fromisoformat(
            ev.get('date', '').replace('Z', '+00:00')
        ).astimezone()
        opp = (
            competitors[1]
            if competitors[0].get('team', {}).get('id') == t_id
            else competitors[0]
        )
        opp_name = opp.get('team', {}).get('shortDisplayName', 'OPP').upper()
        day_str = (
            dt.strftime('%a %I:%M%p')
            .upper()
            .replace('AM', 'A')
            .replace('PM', 'P')
            .lstrip('0')
        )
        return [
            pad_flaps_center(t_name[:15], 15),
            pad_flaps_center(f'NEXT: {day_str}', 15),
            pad_flaps_center(f'vs {opp_name}', 15),
        ]
  except Exception:
    pass

  return [
      pad_flaps_center(t_name[:15], 15),
      pad_flaps_center('NEXT GAME', 15),
      pad_flaps_center('SCHEDULE PENDING', 15),
  ]


def resolve_active_module(config: dict) -> str:
  tz_name = config.get('timezone', 'America/New_York')
  now = (
      datetime.datetime.now(ZoneInfo(tz_name))
      if ZoneInfo
      else datetime.datetime.now()
  )
  current_hm = now.strftime('%H:%M')

  for slot in config.get('routine', []):
    if not slot.get('enabled', True):
      continue
    if slot.get('start_time', '00:00') <= current_hm < slot.get(
        'end_time', '23:59'
    ):
      print(f'Active Slot: {slot.get("name")} -> {slot.get("module")}')
      return slot.get('module')
  return 'weather'


def send_to_vestaboard(lines: list[str], dry_run: bool = False):
  message = '\n'.join(lines)
  if dry_run:
    print('\n'.join(lines))
    return

  key = os.environ.get('VESTABOARD_READ_WRITE_KEY')
  if not key:
    print('Error: VESTABOARD_READ_WRITE_KEY missing!')
    return

  res = requests.post(
      'https://rw.vestaboard.com/',
      headers={'X-Vestaboard-Read-Write-Key': key},
      json={'text': message},
      timeout=10,
  )
  print(f'Status: {res.status_code}')


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--routine', action='store_true')
  parser.add_argument(
      '--module',
      type=str,
      choices=[
          'weather',
          'subway_status',
          'subway_countdown',
          'markets',
          'sports',
      ],
  )
  parser.add_argument(
      '--team', type=str, default='BUF', choices=['BUF', 'NYJ', 'NYG']
  )
  parser.add_argument('--config', type=str, default='config.json')
  parser.add_argument('--test', action='store_true')
  args = parser.parse_args()

  config = {}
  if os.path.exists(args.config):
    with open(args.config, 'r', encoding='utf-8') as f:
      config = json.load(f)

  module_to_run = (
      args.module if args.module else resolve_active_module(config)
  )
  coords = config.get(
      'coordinates', {'latitude': 40.7128, 'longitude': -74.0060}
  )
  team = args.team or config.get('sports', {}).get('active_team', 'BUF')

  if module_to_run == 'weather':
    lines = get_weather(coords['latitude'], coords['longitude'])
  elif module_to_run == 'subway_status':
    lines = get_subway_status()
  elif module_to_run == 'subway_countdown':
    lines = get_subway_countdown()
  elif module_to_run == 'markets':
    lines = get_markets()
  elif module_to_run == 'sports':
    lines = get_sports(team)
  else:
    lines = get_weather(coords['latitude'], coords['longitude'])

  send_to_vestaboard(lines, dry_run=args.test)


if __name__ == '__main__':
  main()
