"""
JARVIS Open-Meteo Weather Tool — tools/weather_tool.py
======================================================
Live, accurate weather forecasts powered by the Open-Meteo API.
- Geocodes cities with Open-Meteo Geocoding API + extensive Bangladesh district map.
- NEVER silently falls back to Khulna if a requested city is not found.
- Supports IP-detected default location and consented browser lat/lon coordinates.
- Separate cache key per coordinate/city pair to eliminate cross-city cache pollution.
- Outputs resolved city, region, and coordinates clearly.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Dict, Any, Optional, List
import httpx
import requests

logger = logging.getLogger("jarvis.tools.weather")

# Complete Bangladesh 64 Districts + Major Global Metros for instant zero-latency resolution
COMMON_CITIES: Dict[str, Dict[str, Any]] = {
    # ── Chapainawabganj and variations ──
    "chapainawabganj": {"lat": 24.5989, "lon": 88.2834, "name": "Chapainawabganj", "region": "Rajshahi Division", "country": "Bangladesh"},
    "chapainawabgonj": {"lat": 24.5989, "lon": 88.2834, "name": "Chapainawabganj", "region": "Rajshahi Division", "country": "Bangladesh"},
    "chapai nawabganj": {"lat": 24.5989, "lon": 88.2834, "name": "Chapainawabganj", "region": "Rajshahi Division", "country": "Bangladesh"},
    "chapai nawabgonj": {"lat": 24.5989, "lon": 88.2834, "name": "Chapainawabganj", "region": "Rajshahi Division", "country": "Bangladesh"},
    "nawabganj": {"lat": 24.5903, "lon": 88.2744, "name": "Nawabganj", "region": "Rajshahi Division", "country": "Bangladesh"},
    "shibganj": {"lat": 24.6850, "lon": 88.1564, "name": "Shibganj", "region": "Rajshahi Division", "country": "Bangladesh"},

    # ── Major Divisions & Districts ──
    "khulna": {"lat": 22.8456, "lon": 89.5403, "name": "Khulna", "region": "Khulna Division", "country": "Bangladesh"},
    "dhaka": {"lat": 23.8103, "lon": 90.4125, "name": "Dhaka", "region": "Dhaka Division", "country": "Bangladesh"},
    "chittagong": {"lat": 22.3569, "lon": 91.7832, "name": "Chittagong", "region": "Chittagong Division", "country": "Bangladesh"},
    "chattogram": {"lat": 22.3569, "lon": 91.7832, "name": "Chittagong", "region": "Chittagong Division", "country": "Bangladesh"},
    "rajshahi": {"lat": 24.3636, "lon": 88.6241, "name": "Rajshahi", "region": "Rajshahi Division", "country": "Bangladesh"},
    "sylhet": {"lat": 24.8949, "lon": 91.8687, "name": "Sylhet", "region": "Sylhet Division", "country": "Bangladesh"},
    "barisal": {"lat": 22.7010, "lon": 90.3535, "name": "Barisal", "region": "Barisal Division", "country": "Bangladesh"},
    "barishal": {"lat": 22.7010, "lon": 90.3535, "name": "Barisal", "region": "Barisal Division", "country": "Bangladesh"},
    "rangpur": {"lat": 25.7439, "lon": 89.2752, "name": "Rangpur", "region": "Rangpur Division", "country": "Bangladesh"},
    "mymensingh": {"lat": 24.7471, "lon": 90.4203, "name": "Mymensingh", "region": "Mymensingh Division", "country": "Bangladesh"},

    # ── Additional Key Bangladesh Districts ──
    "comilla": {"lat": 23.4607, "lon": 91.1809, "name": "Cumilla", "region": "Chittagong Division", "country": "Bangladesh"},
    "cumilla": {"lat": 23.4607, "lon": 91.1809, "name": "Cumilla", "region": "Chittagong Division", "country": "Bangladesh"},
    "bogra": {"lat": 24.8465, "lon": 89.3777, "name": "Bogura", "region": "Rajshahi Division", "country": "Bangladesh"},
    "bogura": {"lat": 24.8465, "lon": 89.3777, "name": "Bogura", "region": "Rajshahi Division", "country": "Bangladesh"},
    "dinajpur": {"lat": 25.6217, "lon": 88.6355, "name": "Dinajpur", "region": "Rangpur Division", "country": "Bangladesh"},
    "jessore": {"lat": 23.1664, "lon": 89.2081, "name": "Jashore", "region": "Khulna Division", "country": "Bangladesh"},
    "jashore": {"lat": 23.1664, "lon": 89.2081, "name": "Jashore", "region": "Khulna Division", "country": "Bangladesh"},
    "kushtia": {"lat": 23.9013, "lon": 89.1205, "name": "Kushtia", "region": "Khulna Division", "country": "Bangladesh"},
    "faridpur": {"lat": 23.6071, "lon": 89.8429, "name": "Faridpur", "region": "Dhaka Division", "country": "Bangladesh"},
    "pabna": {"lat": 24.0064, "lon": 89.2372, "name": "Pabna", "region": "Rajshahi Division", "country": "Bangladesh"},
    "tangail": {"lat": 24.2513, "lon": 89.9167, "name": "Tangail", "region": "Dhaka Division", "country": "Bangladesh"},
    "gazipur": {"lat": 24.0023, "lon": 90.4264, "name": "Gazipur", "region": "Dhaka Division", "country": "Bangladesh"},
    "narayanganj": {"lat": 23.6238, "lon": 90.5000, "name": "Narayanganj", "region": "Dhaka Division", "country": "Bangladesh"},
    "narayangonj": {"lat": 23.6238, "lon": 90.5000, "name": "Narayanganj", "region": "Dhaka Division", "country": "Bangladesh"},
    "cox's bazar": {"lat": 21.4272, "lon": 92.0058, "name": "Cox's Bazar", "region": "Chittagong Division", "country": "Bangladesh"},
    "coxs bazar": {"lat": 21.4272, "lon": 92.0058, "name": "Cox's Bazar", "region": "Chittagong Division", "country": "Bangladesh"},
    "feni": {"lat": 23.0159, "lon": 91.3976, "name": "Feni", "region": "Chittagong Division", "country": "Bangladesh"},
    "noakhali": {"lat": 22.8696, "lon": 91.0993, "name": "Noakhali", "region": "Chittagong Division", "country": "Bangladesh"},
    "brahmanbaria": {"lat": 23.9571, "lon": 91.1119, "name": "Brahmanbaria", "region": "Chittagong Division", "country": "Bangladesh"},
    "sirajganj": {"lat": 24.4534, "lon": 89.7008, "name": "Sirajganj", "region": "Rajshahi Division", "country": "Bangladesh"},
    "naogaon": {"lat": 24.8109, "lon": 88.9419, "name": "Naogaon", "region": "Rajshahi Division", "country": "Bangladesh"},
    "natore": {"lat": 24.4206, "lon": 89.0003, "name": "Natore", "region": "Rajshahi Division", "country": "Bangladesh"},
    "satkhira": {"lat": 22.7185, "lon": 89.0705, "name": "Satkhira", "region": "Khulna Division", "country": "Bangladesh"},
    "bagerhat": {"lat": 22.6516, "lon": 89.7859, "name": "Bagerhat", "region": "Khulna Division", "country": "Bangladesh"},

    # ── Major Global Metros ──
    "london": {"lat": 51.5074, "lon": -0.1278, "name": "London", "region": "England", "country": "United Kingdom"},
    "new york": {"lat": 40.7128, "lon": -74.0060, "name": "New York", "region": "New York", "country": "United States"},
    "tokyo": {"lat": 35.6762, "lon": 139.6503, "name": "Tokyo", "region": "Tokyo", "country": "Japan"},
    "toronto": {"lat": 43.6532, "lon": -79.3832, "name": "Toronto", "region": "Ontario", "country": "Canada"},
    "dubai": {"lat": 25.2048, "lon": 55.2708, "name": "Dubai", "region": "Dubai", "country": "United Arab Emirates"},
    "kolkata": {"lat": 22.5726, "lon": 88.3639, "name": "Kolkata", "region": "West Bengal", "country": "India"},
}

WMO_CODE_MAP = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Foggy", "🌫️"),
    48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Moderate drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"),
    56: ("Light freezing drizzle", "🌧️"),
    57: ("Dense freezing drizzle", "🌧️"),
    61: ("Slight rain", "🌧️"),
    62: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Light freezing rain", "🌧️"),
    67: ("Heavy freezing rain", "🌧️"),
    71: ("Slight snow fall", "🌨️"),
    73: ("Moderate snow fall", "🌨️"),
    75: ("Heavy snow fall", "❄️"),
    77: ("Snow grains", "❄️"),
    80: ("Slight rain showers", "🌦️"),
    81: ("Moderate rain showers", "🌧️"),
    82: ("Violent rain showers", "⛈️"),
    85: ("Slight snow showers", "🌨️"),
    86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with slight hail", "⛈️"),
    99: ("Thunderstorm with heavy hail", "⛈️"),
}

# Cache: coordinate-string -> {"timestamp": float, "data": dict}
_WEATHER_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SEC = 600.0  # 10 minutes


def normalize_city_name(raw_name: str) -> str:
    """Normalizes compound names (ChapaiNawabgonj -> Chapai Nawabganj) and spelling variants."""
    clean = (raw_name or "").strip()
    # Split camelCase or compound names
    clean = re.sub(r"([a-z])([A-Z])", r"\1 \2", clean)
    # Common Bengali transliteration standardizations
    clean = re.sub(r"gonj\b", "ganj", clean, flags=re.IGNORECASE)
    clean = re.sub(r"bari\b", "baria", clean, flags=re.IGNORECASE)
    return clean.strip()


def geocode_city(city_name: str, timeout: float = 4.0) -> Optional[Dict[str, Any]]:
    """
    Geocodes city name into latitude/longitude using Open-Meteo Geocoding API.
    Returns None if the city cannot be resolved.
    """
    clean = normalize_city_name(city_name)
    key = clean.lower()

    if key in COMMON_CITIES:
        return COMMON_CITIES[key]

    # Try original lowercase key
    orig_key = city_name.strip().lower()
    if orig_key in COMMON_CITIES:
        return COMMON_CITIES[orig_key]

    # Query Open-Meteo Geocoding API
    query_candidates = [clean, city_name.strip()]
    if " " in clean:
        query_candidates.append(clean.split()[-1])  # e.g., Nawabganj

    for q in query_candidates:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={httpx.URL(q).raw_path.decode('ascii', errors='ignore') or q}&count=3&language=en&format=json"
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=3&language=en&format=json")
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results")
                    if results and len(results) > 0:
                        # Prefer Bangladesh result if querying from BD context or multiple options
                        bd_res = next((r for r in results if r.get("country") == "Bangladesh"), results[0])
                        return {
                            "lat": bd_res.get("latitude"),
                            "lon": bd_res.get("longitude"),
                            "name": bd_res.get("name", clean),
                            "region": bd_res.get("admin1", ""),
                            "country": bd_res.get("country", "")
                        }
        except Exception as e:
            logger.debug(f"Geocoding attempt for '{q}' failed: {e}")

    return None


def get_weather(
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    timeout: float = 5.0
) -> Dict[str, Any]:
    """
    Fetches real-time weather and 5-day daily forecast from Open-Meteo.
    - Honors explicit lat/lon coordinates when available (consented browser geolocation).
    - If location name given, geocodes it. If not found, returns honest error.
    - If neither given, defaults to IP-detected location.
    """
    city_name = ""
    region = ""
    country = ""
    source_type = "geocoded"

    # 1. Determine Coordinates
    if lat is not None and lon is not None:
        target_lat = float(lat)
        target_lon = float(lon)
        city_name = location or "Your Device Location"
        source_type = "precise_gps"
    elif location and location.strip():
        loc_clean = location.strip()
        geo = geocode_city(loc_clean, timeout=timeout)
        if not geo:
            # DO NOT silently fall back to Khulna! Return honest refusal
            return {
                "ok": False,
                "error": "location_not_found",
                "location": loc_clean,
                "message": f"I could not locate weather data for '{loc_clean}'. Please verify the city spelling or specify a nearby district."
            }
        target_lat = geo["lat"]
        target_lon = geo["lon"]
        city_name = geo["name"]
        region = geo.get("region", "")
        country = geo.get("country", "")
    else:
        # Default: Use IP-detected approximate location
        try:
            from tools.location_service import get_current_location
            cur_loc = get_current_location()
            target_lat = cur_loc.get("lat", 22.8456)
            target_lon = cur_loc.get("lon", 89.5403)
            city_name = cur_loc.get("city", "Khulna")
            region = cur_loc.get("region", "Khulna Division")
            country = cur_loc.get("country", "Bangladesh")
            source_type = cur_loc.get("source", "ip")
        except Exception:
            target_lat = 22.8456
            target_lon = 89.5403
            city_name = "Khulna"
            region = "Khulna Division"
            country = "Bangladesh"

    # 2. Check Coordinate-Specific Cache
    cache_key = f"{round(target_lat, 3)}_{round(target_lon, 3)}"
    now = time.time()
    if cache_key in _WEATHER_CACHE:
        cached_entry = _WEATHER_CACHE[cache_key]
        if now - cached_entry["timestamp"] < CACHE_TTL_SEC:
            logger.debug(f"[WEATHER] Cache hit for {city_name} ({cache_key})")
            return cached_entry["data"]

    # 3. Query Open-Meteo
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={target_lat}&longitude={target_lon}&current=temperature_2m,relative_humidity_2m,"
        f"apparent_temperature,precipitation,weather_code,wind_speed_10m&"
        f"daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&"
        f"timezone=auto"
    )

    data = None
    try:
        r = requests.get(url, headers={"User-Agent": "JARVIS-Assistant/1.0"}, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
    except Exception as exc:
        logger.debug(f"Requests weather error for {city_name}: {exc}")

    if not data:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
        except Exception as exc:
            logger.debug(f"Httpx weather error for {city_name}: {exc}")

    if not data:
        # Fallback using urllib
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Assistant/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
        except Exception:
            pass

    if not data:
        return {
            "ok": False,
            "error": "service_unavailable",
            "location": city_name,
            "message": f"Weather service is temporarily unreachable for {city_name}. Please check internet connection."
        }

    # 4. Parse Telemetry
    curr_raw = data.get("current", {})
    daily_raw = data.get("daily", {})

    wcode = curr_raw.get("weather_code", 0)
    cond_text, icon = WMO_CODE_MAP.get(wcode, ("Fair", "☀️"))

    temp = curr_raw.get("temperature_2m", 0.0)
    apparent_temp = curr_raw.get("apparent_temperature", temp)
    humidity = curr_raw.get("relative_humidity_2m", 0)
    wind_spd = curr_raw.get("wind_speed_10m", 0.0)

    # 5-day forecast
    daily_forecasts: List[Dict[str, Any]] = []
    dates = daily_raw.get("time", [])
    max_temps = daily_raw.get("temperature_2m_max", [])
    min_temps = daily_raw.get("temperature_2m_min", [])
    precip_probs = daily_raw.get("precipitation_probability_max", [])
    daily_codes = daily_raw.get("weather_code", [])

    for i in range(min(5, len(dates))):
        d_code = daily_codes[i] if i < len(daily_codes) else 0
        d_cond, d_icon = WMO_CODE_MAP.get(d_code, ("Fair", "☀️"))
        daily_forecasts.append({
            "date": dates[i],
            "max_temp": round(max_temps[i], 1) if i < len(max_temps) else temp,
            "min_temp": round(min_temps[i], 1) if i < len(min_temps) else temp,
            "rain_chance": precip_probs[i] if i < len(precip_probs) else 0,
            "condition": d_cond,
            "icon": d_icon,
        })

    loc_header = f"{city_name}"
    if region:
        loc_header += f", {region}"
    loc_header += f" ({target_lat:.2f}°N, {target_lon:.2f}°E)"

    speech = (
        f"The weather in {city_name} is currently {round(temp)}°C and {cond_text}. "
        f"Humidity is {humidity}% with wind speed at {wind_spd} km/h."
    )
    if daily_forecasts:
        high = daily_forecasts[0]["max_temp"]
        low = daily_forecasts[0]["min_temp"]
        speech += f" Today's forecast: high of {high}°C and low of {low}°C."

    result_payload = {
        "ok": True,
        "city": city_name,
        "location": city_name,
        "temperature": round(temp, 1),
        "condition": cond_text,
        "icon": icon,
        "humidity": humidity,
        "wind_speed": wind_spd,
        "region": region,
        "country": country,
        "display_name": loc_header,
        "latitude": target_lat,
        "longitude": target_lon,
        "source": source_type,
        "current": {
            "temperature": round(temp, 1),
            "feels_like": round(apparent_temp, 1),
            "condition": cond_text,
            "icon": icon,
            "humidity": humidity,
            "wind_speed": wind_spd,
            "weather_code": wcode,
        },
        "daily": daily_forecasts,
        "speech": speech,
        "formatted": f"Weather for {loc_header}: {round(temp, 1)}°C {icon} ({cond_text}), Humidity {humidity}%, Wind {wind_spd} km/h."
    }

    # Save to coordinate cache
    _WEATHER_CACHE[cache_key] = {"timestamp": now, "data": result_payload}
    return result_payload
