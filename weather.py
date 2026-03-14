"""
Weather Data Fetcher
=====================
Fetches weather forecasts from FREE APIs (no API key needed).
- NWS API: US cities only (api.weather.gov)
- Open-Meteo: Worldwide (open-meteo.com)
"""

import requests
from time import sleep
from config import NWS_API, OPEN_METEO_API, CITIES

USER_AGENT = "(polymarket-weather-bot, weather-bot@example.com)"


def get_forecast_open_meteo(lat, lon, days=3):
    """
    Get weather forecast from Open-Meteo (works worldwide, no API key).
    Returns daily high/low temps and precipitation probability.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
        "forecast_days": days,
    }

    try:
        resp = requests.get(OPEN_METEO_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        forecasts = []

        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        precip_probs = daily.get("precipitation_probability_max", [])
        precip_sums = daily.get("precipitation_sum", [])

        for i in range(len(dates)):
            forecasts.append({
                "date": dates[i],
                "high_f": highs[i] if i < len(highs) else None,
                "low_f": lows[i] if i < len(lows) else None,
                "high_c": round((highs[i] - 32) * 5 / 9, 1) if i < len(highs) and highs[i] else None,
                "low_c": round((lows[i] - 32) * 5 / 9, 1) if i < len(lows) and lows[i] else None,
                "precip_probability": precip_probs[i] if i < len(precip_probs) else None,
                "precip_mm": precip_sums[i] if i < len(precip_sums) else None,
            })

        return forecasts

    except Exception as e:
        print(f"  [ERROR] Open-Meteo failed: {e}")
        return []


def get_forecast_nws(lat, lon):
    """
    Get weather forecast from NWS (US cities only, no API key).
    Returns daily forecast periods.
    """
    headers = {"User-Agent": USER_AGENT}

    try:
        # Step 1: Get grid point
        points_url = f"{NWS_API}/points/{lat},{lon}"
        resp = requests.get(points_url, headers=headers, timeout=10)
        resp.raise_for_status()
        points = resp.json()

        forecast_url = points["properties"]["forecast"]
        sleep(0.5)  # Rate limiting

        # Step 2: Get forecast
        resp = requests.get(forecast_url, headers=headers, timeout=10)
        resp.raise_for_status()
        forecast_data = resp.json()

        forecasts = []
        for period in forecast_data["properties"]["periods"]:
            forecasts.append({
                "name": period["name"],
                "date": period["startTime"][:10],
                "temp_f": period["temperature"],
                "temp_unit": period["temperatureUnit"],
                "is_daytime": period["isDaytime"],
                "wind": period["windSpeed"],
                "short_forecast": period["shortForecast"],
                "precip_probability": period.get("probabilityOfPrecipitation", {}).get("value"),
            })

        return forecasts

    except Exception as e:
        print(f"  [ERROR] NWS failed: {e}")
        return []


def get_forecast(city_name, lat, lon, country):
    """
    Get forecast for a city. Uses NWS for US, Open-Meteo for everywhere else.
    Returns standardized forecast data.
    """
    if country == "US":
        nws_data = get_forecast_nws(lat, lon)
        if nws_data:
            # Convert NWS format to standard format
            # NWS gives separate daytime/nighttime periods
            forecasts = []
            day_temps = {}

            for period in nws_data:
                date = period["date"]
                if date not in day_temps:
                    day_temps[date] = {"high_f": None, "low_f": None, "precip_probability": None}

                if period["is_daytime"]:
                    day_temps[date]["high_f"] = period["temp_f"]
                    day_temps[date]["precip_probability"] = period["precip_probability"]
                else:
                    day_temps[date]["low_f"] = period["temp_f"]

            for date, temps in day_temps.items():
                high = temps["high_f"]
                low = temps["low_f"]
                forecasts.append({
                    "date": date,
                    "high_f": high,
                    "low_f": low,
                    "high_c": round((high - 32) * 5 / 9, 1) if high else None,
                    "low_c": round((low - 32) * 5 / 9, 1) if low else None,
                    "precip_probability": temps["precip_probability"],
                    "precip_mm": None,  # NWS doesn't give this easily
                })

            return forecasts

    # Fallback / non-US: use Open-Meteo
    return get_forecast_open_meteo(lat, lon)


def get_all_forecasts():
    """
    Fetch forecasts for all configured cities.
    Returns dict: {city_name: [forecast_days]}
    """
    all_forecasts = {}

    for name, lat, lon, country in CITIES:
        print(f"  Fetching forecast for {name}...")
        forecasts = get_forecast(name, lat, lon, country)
        all_forecasts[name] = forecasts
        sleep(0.5)  # Be nice to the APIs

    return all_forecasts


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 50)
    print("WEATHER FORECAST TEST")
    print("=" * 50)

    forecasts = get_all_forecasts()

    for city, days in forecasts.items():
        print(f"\n--- {city} ---")
        for day in days[:3]:  # Show next 3 days
            high = day.get("high_f", "?")
            low = day.get("low_f", "?")
            precip = day.get("precip_probability", "?")
            print(f"  {day['date']}: High {high}F / Low {low}F | Rain: {precip}%")

    print(f"\nTotal cities fetched: {len(forecasts)}")
