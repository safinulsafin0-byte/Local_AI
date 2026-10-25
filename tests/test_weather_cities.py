import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.weather_tool import get_weather

cities = ['Khulna', 'Dhaka', 'ChapaiNawabgonj', 'Rajshahi', 'FakeNonExistentCity123']
results = {}

for city in cities:
    res = get_weather(city)
    if res.get('ok'):
        disp = res.get('display_name')
        t = res['current']['temperature']
        c = res['current']['condition']
        results[city] = (disp, t, c)
        print(f"PASS: {city} -> {disp}: {t}°C, {c}")
    else:
        results[city] = None
        print(f"PASS (Honest Not Found): {city} -> {res.get('message')}")

# Verify 4 real cities all returned different coordinates
coords = [get_weather(c)['latitude'] for c in ['Khulna', 'Dhaka', 'ChapaiNawabgonj', 'Rajshahi']]
assert len(set(coords)) == 4, f"Coordinates collided! {coords}"
assert results['FakeNonExistentCity123'] is None, "Fake city should have returned ok=False"
print("\nALL WEATHER TESTS PASSED! Distinct coordinates, zero fallback pollution, honest not found.")

