"""
Polymarket Market Scanner
==========================
Fetches and parses markets from the Gamma API (free, no auth needed).
Handles both weather markets and all markets (for long shots).
"""

import re
import json
import requests
from config import GAMMA_API


def _parse_json_field(value):
    """Parse fields that the Gamma API returns as JSON strings."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _normalize_market(market):
    """Normalize a market dict — parse JSON-string fields into real lists."""
    for field in ("outcomePrices", "outcomes", "clobTokenIds"):
        if field in market:
            market[field] = _parse_json_field(market[field])
    return market


def fetch_markets(limit=100, offset=0, active=True):
    """
    Fetch markets from the Gamma API.
    Returns list of market dicts.
    """
    params = {
        "limit": limit,
        "offset": offset,
        "active": str(active).lower(),
        "closed": "false",
    }

    try:
        resp = requests.get(f"{GAMMA_API}/markets", params=params, timeout=15)
        resp.raise_for_status()
        markets = resp.json()
        return [_normalize_market(m) for m in markets]
    except Exception as e:
        print(f"  [ERROR] Gamma API failed: {e}")
        return []


def fetch_all_markets(max_pages=10):
    """
    Fetch all active markets (paginated).
    Returns combined list.
    """
    all_markets = []
    for page in range(max_pages):
        offset = page * 100
        markets = fetch_markets(limit=100, offset=offset)
        if not markets:
            break
        all_markets.extend(markets)
        if len(markets) < 100:
            break  # Last page

    return all_markets


def fetch_events(limit=100, offset=0):
    """
    Fetch events from the Gamma API. Events group related markets.
    """
    params = {
        "limit": limit,
        "offset": offset,
        "active": "true",
        "closed": "false",
    }

    try:
        resp = requests.get(f"{GAMMA_API}/events", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [ERROR] Gamma API events failed: {e}")
        return []


def is_weather_market(market):
    """
    Check if a market is weather-related based on title/tags.
    """
    title = (market.get("question") or market.get("title") or "").lower()
    tags = [t.get("label", "").lower() for t in market.get("tags", [])]

    weather_keywords = [
        "temperature", "weather", "rain", "snow", "precipitation",
        "high above", "high below", "low above", "low below",
        "degrees", "°f", "°c", "hurricane", "tornado", "storm",
        "heat", "cold", "freeze", "frost",
    ]

    if "weather" in tags or "climate" in tags:
        return True

    return any(kw in title for kw in weather_keywords)


def parse_weather_market(market):
    """
    Parse a weather market title to extract structured data.
    Example: "Will the high temperature in New York exceed 72°F on March 15?"
    Returns: {city, metric, threshold, unit, date, direction}
    """
    title = market.get("question") or market.get("title") or ""

    # Try to extract city
    city = None
    known_cities = [
        "New York", "NYC", "Chicago", "Los Angeles", "LA",
        "London", "Paris", "Seoul", "Buenos Aires", "Tokyo",
        "Sydney", "Berlin", "Miami", "Houston", "San Francisco",
    ]
    for c in known_cities:
        if c.lower() in title.lower():
            city = c
            break

    # Try to extract temperature threshold
    temp_match = re.search(r'(\d+\.?\d*)\s*°?\s*([FCfc])', title)
    threshold = float(temp_match.group(1)) if temp_match else None
    unit = temp_match.group(2).upper() if temp_match else None

    # Try to extract direction (above/below/exceed)
    direction = None
    if any(w in title.lower() for w in ["exceed", "above", "over", "higher than", "at least"]):
        direction = "above"
    elif any(w in title.lower() for w in ["below", "under", "lower than", "less than"]):
        direction = "below"

    # Try to extract metric (high/low temp, precipitation)
    metric = None
    if "high" in title.lower():
        metric = "high_temp"
    elif "low" in title.lower():
        metric = "low_temp"
    elif "precip" in title.lower() or "rain" in title.lower():
        metric = "precipitation"

    # Try to extract date
    date_match = re.search(
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})',
        title, re.IGNORECASE
    )
    date_str = None
    if date_match:
        month_name = date_match.group(1)
        day = date_match.group(2)
        months = {
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12"
        }
        month_num = months.get(month_name.lower(), "01")
        date_str = f"2026-{month_num}-{day.zfill(2)}"

    return {
        "title": title,
        "city": city,
        "metric": metric,
        "threshold": threshold,
        "unit": unit,
        "direction": direction,
        "date": date_str,
        "market_id": market.get("id"),
        "token_ids": market.get("clobTokenIds", []),
        "outcomes": market.get("outcomes", []),
        "outcomePrices": market.get("outcomePrices", []),
        "volume": float(market.get("volume", 0) or 0),
        "end_date": market.get("endDate"),
    }


def get_weather_markets():
    """
    Fetch all active weather markets, parsed and ready for analysis.
    """
    print("  Scanning for weather markets...")
    all_markets = fetch_all_markets()
    weather = []

    for m in all_markets:
        if is_weather_market(m):
            parsed = parse_weather_market(m)
            # Only include if we could parse something useful
            if parsed["city"] and parsed["threshold"] is not None:
                weather.append(parsed)

    print(f"  Found {len(weather)} parseable weather markets")
    return weather


def get_market_prices(market):
    """
    Extract YES/NO prices from a market.
    Returns (yes_price, no_price) or (None, None).
    """
    prices = market.get("outcomePrices", [])
    if len(prices) >= 2:
        try:
            return float(prices[0]), float(prices[1])
        except (ValueError, TypeError):
            pass
    return None, None


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("POLYMARKET MARKET SCANNER TEST")
    print("=" * 60)

    # Test: fetch all markets
    print("\nFetching all active markets...")
    all_markets = fetch_all_markets(max_pages=5)
    print(f"Total active markets found: {len(all_markets)}")

    # Test: filter weather markets
    print("\nFiltering weather markets...")
    weather = get_weather_markets()

    print(f"\n--- WEATHER MARKETS ({len(weather)}) ---")
    for w in weather[:15]:  # Show first 15
        yes_price, no_price = get_market_prices(w)
        print(f"\n  {w['title']}")
        print(f"    City: {w['city']} | Metric: {w['metric']} | Threshold: {w['threshold']} {w['unit']}")
        print(f"    Direction: {w['direction']} | Date: {w['date']}")
        print(f"    YES: ${yes_price} | NO: ${no_price} | Volume: ${w['volume']:,.0f}")

    # Test: show all markets with low prices (for long shot preview)
    print(f"\n--- LOW PRICE MARKETS (<=5c) ---")
    low_price_count = 0
    for m in all_markets:
        prices = m.get("outcomePrices", [])
        if prices:
            try:
                yes_price = float(prices[0])
                if yes_price <= 0.05 and yes_price > 0:
                    title = m.get("question") or m.get("title") or "?"
                    vol = float(m.get("volume", 0) or 0)
                    multiplier = round(1 / yes_price, 1) if yes_price > 0 else 0
                    print(f"  [{yes_price:.2f}c] (x{multiplier}) {title[:80]}  [Vol: ${vol:,.0f}]")
                    low_price_count += 1
            except (ValueError, TypeError):
                pass

    print(f"\nTotal low-price markets: {low_price_count}")
