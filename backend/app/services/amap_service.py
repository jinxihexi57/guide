"""Amap HTTP service wrapper."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings
from ..models.schemas import Location, POIInfo, WeatherInfo
from ..utils.ttl_cache import TTLCache

_HTTP_TIMEOUT = 15.0
_AMAP_BASE_URL = "https://restapi.amap.com"
_POI_CACHE: TTLCache[tuple, List[POIInfo]] = TTLCache(default_ttl_seconds=30 * 60, max_size=512)
_WEATHER_CACHE: TTLCache[str, Dict[str, Any] | List[WeatherInfo]] = TTLCache(default_ttl_seconds=30 * 60, max_size=128)


class AmapService:
    """Amap HTTP service wrapper."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.amap_api_key:
            raise ValueError("高德地图 API Key 未配置，请在 .env 中设置 AMAP_API_KEY")

        self.api_key = settings.amap_api_key
        self.base_url = _AMAP_BASE_URL
        self.timeout = _HTTP_TIMEOUT

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        query = {"key": self.api_key, **params}
        with httpx.Client(base_url=self.base_url, timeout=self.timeout, trust_env=False) as client:
            response = client.get(path, params=query)
            response.raise_for_status()
            data = response.json()

        if str(data.get("status", "1")) != "1":
            raise ValueError(data.get("info") or "高德接口返回失败")
        return data

    @staticmethod
    def _parse_location(raw_location: str) -> Optional[Dict[str, float]]:
        if not raw_location or "," not in raw_location:
            return None
        try:
            longitude, latitude = raw_location.split(",", 1)
            return {"longitude": float(longitude), "latitude": float(latitude)}
        except ValueError:
            return None

    def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> List[POIInfo]:
        cache_key = (keywords, city, citylimit)
        cached = _POI_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            data = self._get(
                "/v3/place/text",
                {
                    "keywords": keywords,
                    "city": city,
                    "citylimit": "true" if citylimit else "false",
                    "offset": 6,
                    "page": 1,
                    "extensions": "base",
                },
            )
            pois = data.get("pois", [])
            parsed_pois: List[Dict[str, Any]] = []

            for poi in pois:
                location = self._parse_location(poi.get("location", ""))
                if location is None:
                    continue
                parsed_pois.append(
                    {
                        "id": poi.get("id") or "",
                        "name": poi.get("name") or "",
                        "type": poi.get("type") or poi.get("typecode") or "",
                        "address": poi.get("address") or poi.get("adname") or "",
                        "location": location,
                        "tel": poi.get("tel"),
                    }
                )

            _POI_CACHE.set(cache_key, parsed_pois, ttl_seconds=30 * 60)
            return parsed_pois
        except Exception as exc:
            print(f"POI search failed: {exc}")
            return cached or []

    def get_weather(self, city: str) -> Dict[str, Any] | List[WeatherInfo]:
        cached = _WEATHER_CACHE.get(city)
        if cached is not None:
            return cached

        try:
            data = self._get(
                "/v3/weather/weatherInfo",
                {
                    "city": city,
                    "extensions": "all",
                    "output": "JSON",
                },
            )
            forecasts = data.get("forecasts", [])
            forecast_root = forecasts[0] if forecasts else {}
            casts = forecast_root.get("casts", [])

            weather_list: List[Dict[str, Any]] = []
            for item in casts:
                weather_list.append(
                    {
                        "date": item.get("date", ""),
                        "day_weather": item.get("dayweather") or "",
                        "night_weather": item.get("nightweather") or "",
                        "day_temp": item.get("daytemp") or "",
                        "night_temp": item.get("nighttemp") or "",
                        "wind_direction": item.get("daywind") or "",
                        "wind_power": item.get("daypower") or "",
                    }
                )

            result = {
                "city": forecast_root.get("city", city),
                "update_time": forecast_root.get("reporttime", ""),
                "forecast": weather_list,
            }
            _WEATHER_CACHE.set(city, result, ttl_seconds=30 * 60)
            return result
        except Exception as exc:
            print(f"Weather lookup failed: {exc}")
            return cached or []

    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        try:
            params: Dict[str, Any] = {"address": address}
            if city:
                params["city"] = city
            data = self._get("/v3/geocode/geo", params)
            geocodes = data.get("geocodes", [])
            if not geocodes:
                return None
            location = self._parse_location(geocodes[0].get("location", ""))
            if location is None:
                return None
            return Location(**location)
        except Exception as exc:
            print(f"Geocode failed: {exc}")
            return None

    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking",
    ) -> Dict[str, Any]:
        try:
            origin = self.geocode(origin_address, origin_city)
            destination = self.geocode(destination_address, destination_city)
            if not origin or not destination:
                return {}

            origin_loc = f"{origin.longitude},{origin.latitude}"
            destination_loc = f"{destination.longitude},{destination.latitude}"

            if route_type == "driving":
                data = self._get("/v3/direction/driving", {"origin": origin_loc, "destination": destination_loc})
                paths = data.get("route", {}).get("paths", [])
                if not paths:
                    return {}
                first = paths[0]
                distance = float(first.get("distance", 0))
                duration = int(float(first.get("duration", 0)))
            elif route_type == "transit":
                city = origin_city or destination_city or ""
                data = self._get(
                    "/v3/direction/transit/integrated",
                    {"origin": origin_loc, "destination": destination_loc, "city": city},
                )
                transits = data.get("route", {}).get("transits", [])
                if not transits:
                    return {}
                first = transits[0]
                distance = float(first.get("distance", 0))
                duration = int(float(first.get("duration", 0)))
            else:
                data = self._get("/v3/direction/walking", {"origin": origin_loc, "destination": destination_loc})
                paths = data.get("route", {}).get("paths", [])
                if not paths:
                    return {}
                first = paths[0]
                distance = float(first.get("distance", 0))
                duration = int(float(first.get("duration", 0)))

            return {
                "distance": distance,
                "duration": duration,
                "route_type": route_type,
                "description": f"{origin_address} 到 {destination_address} 的 {route_type} 路线",
            }
        except Exception as exc:
            print(f"Route planning failed: {exc}")
            return {}

    def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
        try:
            data = self._get("/v5/place/detail", {"id": poi_id, "show_fields": "business,indoor,navi,photos"})
            pois = data.get("pois", [])
            return pois[0] if pois else {}
        except Exception as exc:
            print(f"POI detail lookup failed: {exc}")
            return {}

    def get_runtime_status(self) -> Dict[str, Any]:
        return {
            "provider": "amap-http",
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
        }


_amap_service: AmapService | None = None


def get_amap_service() -> AmapService:
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service
