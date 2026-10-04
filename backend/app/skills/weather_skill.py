"""Weather lookup skill."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from hello_agents.tools import Tool, ToolParameter

from ..services.amap_service import get_amap_service


class WeatherSkill(Tool):
    """Fetch and normalize multi-day weather data."""

    def __init__(self) -> None:
        super().__init__(
            name="weather_query",
            description="查询指定城市的多天天气，并输出结构化结果",
        )
        self.amap_service = get_amap_service()

    def run(self, parameters: Dict[str, Any]) -> str:
        city = parameters.get("city")
        if not city:
            return json.dumps({"error": "请提供城市名称"}, ensure_ascii=False)
        return json.dumps(self.get_candidates(city), ensure_ascii=False, indent=2)

    def get_parameters(self) -> List[ToolParameter]:
        return [ToolParameter(name="city", type="string", description="城市名称", required=True)]

    def get_candidates(self, city: str) -> Dict[str, Any]:
        weather_info = self.amap_service.get_weather(city)
        if not isinstance(weather_info, dict):
            return {"city": city, "update_time": "", "forecast": []}
        return {
            "city": weather_info.get("city", city),
            "update_time": weather_info.get("update_time", ""),
            "forecast": weather_info.get("forecast", []),
        }
