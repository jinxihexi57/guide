"""Attraction recommendation skill."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from hello_agents.tools import Tool, ToolParameter

from ..services.amap_service import get_amap_service


class AttractionSkill(Tool):
    """Search and normalize attraction candidates."""

    def __init__(self) -> None:
        super().__init__(
            name="attraction_search",
            description="搜索指定城市的景点候选，并输出结构化结果",
        )
        self.amap_service = get_amap_service()

    def run(self, parameters: Dict[str, Any]) -> str:
        city = parameters.get("city")
        keywords = parameters.get("keywords", "景点")
        if not city:
            return json.dumps({"error": "请提供城市名称"}, ensure_ascii=False)
        return json.dumps(
            self.get_candidates(city=city, keywords=keywords),
            ensure_ascii=False,
            indent=2,
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="city", type="string", description="城市名称", required=True),
            ToolParameter(name="keywords", type="string", description="景点偏好关键词", required=False, default="景点"),
        ]

    def get_candidates(self, city: str, keywords: str = "景点", limit: int = 12) -> List[Dict[str, Any]]:
        pois = self.amap_service.search_poi(keywords, city)
        candidates: List[Dict[str, Any]] = []
        for poi in pois[:limit]:
            category = poi.get("type") or keywords or "景点"
            candidates.append(
                {
                    "name": poi.get("name") or "未知景点",
                    "address": poi.get("address") or f"{city}市区",
                    "location": poi.get("location"),
                    "visit_duration": self._estimate_visit_duration(category),
                    "description": f"适合{keywords}主题行程的候选景点",
                    "category": category,
                    "ticket_price": self._estimate_ticket_price(category),
                }
            )
        return candidates

    @staticmethod
    def _estimate_visit_duration(category: str) -> int:
        text = category.lower()
        if "博物馆" in category or "museum" in text:
            return 180
        if "公园" in category or "park" in text:
            return 120
        if "古迹" in category or "景区" in category:
            return 150
        return 120

    @staticmethod
    def _estimate_ticket_price(category: str) -> int:
        if "博物馆" in category:
            return 50
        if "景区" in category or "故宫" in category:
            return 80
        return 30
