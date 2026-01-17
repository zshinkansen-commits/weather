from flask import Flask, request, Response
import datetime as dt
import xml.sax.saxutils as sx
import requests
import xml.etree.ElementTree as ET
import os

app = Flask(__name__)

# --- Configuration ---
OPENMETEO_WEATHER = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"

# --- 1. The Mapper ---
def get_weather_info(code: int, is_night: bool):
    """Returns (IconID, WeatherText) based on your Java Switch Case."""
    # Mapping WMO Code - (DayIcon, NightIcon, Text)
    wmo_map = {
        0: (1, 33, "Sunny" if not is_night else "Clear"),
        1: (2, 34, "Mostly Sunny" if not is_night else "Mostly Clear"),
        2: (3, 35, "Partly Sunny" if not is_night else "Partly Cloudy"),
        3: (6, 38, "Mostly Cloudy"),
        45: (11, 11, "Fog"),
        48: (11, 11, "Fog"),
        51: (12, 39, "Showers" if not is_night else "Partly Cloudy with Showers"),
        53: (12, 40, "Showers" if not is_night else "Mostly Cloudy with Showers"),
        55: (12, 40, "Showers"),
        61: (18, 18, "Rain"),
        63: (18, 18, "Rain"),
        65: (18, 18, "Rain"),
        71: (22, 44, "Snow" if not is_night else "Mostly Cloudy with Snow"),
        73: (22, 44, "Snow"),
        75: (22, 44, "Snow"),
        80: (12, 39, "Showers"),
        95: (15, 41, "Thunderstorms" if not is_night else "Partly Cloudy with Thunder Showers"),
    }
    icon_d, icon_n, text = wmo_map.get(code, (7, 38, "Cloudy"))
    icon_id = icon_n if is_night else icon_d
    return icon_id, text

# --- 2. The City Search ---
@app.route("/widget/samsungmobile/city-find.asp")
def city_find():
    q = request.args.get("location", "").strip()
    lat_p = request.args.get("latitude")
    lon_p = request.args.get("longitude")

    if lat_p and lon_p:
        results = [{"name": "Current Location", "admin1": "GPS", "latitude": lat_p, "longitude": lon_p, "id": "gps"}]
    elif q and request.args.get("returnGeoPosition") == "1":
        r = requests.get(OPENMETEO_GEOCODE, params={"name": q, "count": 10, "language": "en"}).json()
        results = r.get("results") or []
    else:
        results = []

    root = ET.Element("citylist", intl="1")
    for idx, r in enumerate(results, start=1):
        loc_str = f"loc:{r['latitude']},{r['longitude']}"
        state = f"{r.get('admin1', '')} ({r.get('country', '')})"
        ET.SubElement(root, "location", cnt=str(idx), city=r['name'], state=state, 
                      location=loc_str, latitude=str(r['latitude']), longitude=str(r['longitude']))
    
    return Response(ET.tostring(root, encoding="utf-8", xml_declaration=True), mimetype="text/xml")

# --- 3. The Weather Engine ---
@app.route("/widget/samsungmobile/weather-data.asp")
@app.route("/widget/samsungmobile/briefing_weather.asp")
def weather_data():
    loc_param = request.args.get("location", "")
    metric = int(request.args.get("metric", 0))
    
    try:
        if "loc:" in loc_param:
            coords = loc_param.replace("loc:", "").split(",")
            lat, lon = float(coords[0]), float(coords[1])
        else:
            lat, lon = 53.4839, -2.2446
    except:
        lat, lon = 53.4839, -2.2446

    w = requests.get(OPENMETEO_WEATHER, params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,weather_code,is_day",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,sunrise,sunset",
        "timezone": "auto"
    }).json()

    curr = w["current"]
    is_night = curr["is_day"] == 0
    icon_id, weather_text = get_weather_info(curr["weather_code"], is_night)
    
    offset_seconds = w.get("utc_offset_seconds", 0)
    local_city_time = int(dt.datetime.now(dt.timezone.utc).timestamp() + offset_seconds)

    def fmt_temp(c):
        val = (c * 9/5 + 32) if metric == 0 else c
        return f"{val:.1f}".rstrip('0').rstrip('.')

    daily = w["daily"]
    forecast_xml = ""
    for i in range(min(7, len(daily["weather_code"]))):
        f_icon, _ = get_weather_info(daily["weather_code"][i], False)
        forecast_xml += f"""
    <daytime>
      <weathericon>{f_icon}</weathericon>
      <hightemperature>{fmt_temp(daily['temperature_2m_max'][i])}</hightemperature>
      <lowtemperature>{fmt_temp(daily['temperature_2m_min'][i])}</lowtemperature>
    </daytime>"""

    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<response>
  <local>
    <currentGmtOffset>{int(offset_seconds / 3600)}</currentGmtOffset>
    <time>{local_city_time}</time>
    <obsDaylight>{curr['is_day']}</obsDaylight>
    <isDaylight>{curr['is_day']}</isDaylight>
    <planets><sun rise="{daily['sunrise'][0].split('T')[1]}" set="{daily['sunset'][0].split('T')[1]}" /></planets>
  </local>
  <currentconditions>
    <temperature>{fmt_temp(curr['temperature_2m'])}</temperature>
    <weathertext>{sx.escape(weather_text)}</weathertext>
    <weathericon>{icon_id}</weathericon>
    <url>http://www.accuweather.com</url>
  </currentconditions>
  <forecast>
    <dayurl>http://www.accuweather.com</dayurl>
    {forecast_xml}
  </forecast>
</response>"""
    return Response(body, mimetype="text/xml")

# Root route for Render Health Check
@app.route("/")
def home():
    return "Weather Bridge is Online", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port)

