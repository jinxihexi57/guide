"""Hotel recommendation skill."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from hello_agents.tools import Tool, ToolParameter

from ..services.amap_service import get_amap_service


class HotelSkill(Tool):
    """Search and normalize hotel candidates."""

    def __init__(self) -> None:
        super().__init__(
            name="hotel_search",
            description="搜索指定城市的酒店候选，并输出结构化结果",
        )
        self.amap_service = get_amap_service()

    def run(self, parameters: Dict[str, Any]) -> str:
        city = parameters.get("city")
        hotel_type = parameters.get("type", "酒店")
        if not city:
            return json.dumps({"error": "请提供城市名称"}, ensure_ascii=False)
        return json.dumps(
            self.get_candidates(city=city, hotel_type=hotel_type),
            ensure_ascii=False,
            indent=2,
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="city", type="string", description="城市名称", required=True),
            ToolParameter(name="type", type="string", description="住宿偏好，如酒店、民宿、舒适型酒店", required=False, default="酒店"),
        ]

    def get_candidates(self, city: str, hotel_type: str = "酒店", limit: int = 8) -> List[Dict[str, Any]]:
        pois = self.amap_service.search_poi(hotel_type, city)
        candidates: List[Dict[str, Any]] = []
        for poi in pois[:limit]:
            candidates.append(
                {
                    "name": poi.get("name") or "未知酒店",
                    "address": poi.get("address") or f"{city}市区",
                    "location": poi.get("location"),
                    "price_range": self._estimate_price_range(hotel_type),
                    "rating": "4.5",
                    "distance": "待规划时结合景点估算",
                    "type": hotel_type,
                    "estimated_cost": self._estimate_cost(hotel_type),
                }
            )
        return candidates

    @staticmethod
    def _estimate_price_range(hotel_type: str) -> str:
        if "豪华" in hotel_type:
            return "800-1200元"
        if "舒适" in hotel_type:
            return "400-700元"
        if "民宿" in hotel_type:
            return "300-600元"
        return "200-400元"

    @staticmethod
    def _estimate_cost(hotel_type: str) -> int:
        if "豪华" in hotel_type:
            return 1000
        if "舒适" in hotel_type:
            return 550
        if "民宿" in hotel_type:
            return 450
        return 300
