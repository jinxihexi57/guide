"""Food recommendation skill."""

from __future__ import annotations

from typing import Any, Dict, List

from hello_agents.tools import Tool, ToolParameter

from ..services.amap_service import get_amap_service


class FoodSkill(Tool):
    """Search and format meal candidates for the planner."""

    def __init__(self) -> None:
        super().__init__(
            name="food_search",
            description="搜索指定城市的餐饮场所，并按餐别提供候选",
        )
        self.amap_service = get_amap_service()

    def run(self, parameters: Dict[str, Any]) -> str:
        """Execute restaurant search and return grouped meal candidates."""
        city = parameters.get("city")
        cuisine = parameters.get("cuisine", "餐厅")
        meal_type = parameters.get("meal_type", "")
        preferences = parameters.get("preferences", [])

        if not city:
            return "错误: 请提供城市名称"

        try:
            restaurants_by_meal = self.get_candidates(city, cuisine, meal_type, preferences)
            return self._format_food_response(restaurants_by_meal)
        except Exception as exc:
            return f"搜索餐饮场所失败: {exc}"

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="city",
                type="string",
                description="城市名称",
                required=True,
            ),
            ToolParameter(
                name="cuisine",
                type="string",
                description="餐饮类型，如'餐厅'、'川菜'、'粤菜'等",
                required=False,
                default="餐厅",
            ),
            ToolParameter(
                name="meal_type",
                type="string",
                description="餐别，可选 breakfast/lunch/dinner",
                required=False,
                default="",
            ),
            ToolParameter(
                name="preferences",
                type="array",
                description="用户偏好标签列表",
                required=False,
                default=[],
            ),
        ]

    def get_candidates(
        self,
        city: str,
        cuisine: str = "餐厅",
        meal_type: str = "",
        preferences: List[str] | None = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return self._search_restaurants(city, cuisine, meal_type, preferences or [])

    def _search_restaurants(
        self,
        city: str,
        cuisine: str,
        meal_type: str,
        preferences: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        if meal_type:
            keywords = self._keywords_for_meal(meal_type, cuisine, preferences)
            return {meal_type: self._search_with_keywords(city, keywords)}

        return {
            "breakfast": self._search_with_keywords(city, self._keywords_for_meal("breakfast", cuisine, preferences)),
            "lunch": self._search_with_keywords(city, self._keywords_for_meal("lunch", cuisine, preferences)),
            "dinner": self._search_with_keywords(city, self._keywords_for_meal("dinner", cuisine, preferences)),
        }

    def _search_with_keywords(self, city: str, keywords: List[str]) -> List[Dict[str, Any]]:
        seen_names: set[str] = set()
        merged: List[Dict[str, Any]] = []

        for keyword in keywords:
            for restaurant in self.amap_service.search_poi(keyword, city):
                name = restaurant.get("name", "").strip()
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                merged.append(restaurant)
                if len(merged) >= 6:
                    return merged

        return merged

    @staticmethod
    def _keywords_for_meal(meal_type: str, cuisine: str, preferences: List[str]) -> List[str]:
        food_preference = "美食" in preferences if preferences else False

        if meal_type == "breakfast":
            keywords = ["早餐", "早点", "早餐店", "包子铺"]
            if food_preference:
                keywords.append("老字号早餐")
        elif meal_type == "lunch":
            keywords = [cuisine, "家常菜", "本地菜"]
        elif meal_type == "dinner":
            keywords = [cuisine, "特色菜", "餐馆"]
        else:
            keywords = [cuisine, "餐厅"]

        deduped: List[str] = []
        for keyword in keywords:
            if keyword and keyword not in deduped:
                deduped.append(keyword)
        return deduped

    def _format_food_response(self, restaurants_by_meal: Dict[str, List[Dict[str, Any]]]) -> str:
        if not restaurants_by_meal:
            return "未搜索到餐饮场所信息"

        meal_titles = {
            "breakfast": "早餐候选",
            "lunch": "午餐候选",
            "dinner": "晚餐候选",
        }

        result: List[str] = []
        result.append("餐饮候选信息")
        result.append("请优先保证多天行程中的早餐、午餐、晚餐有变化，不要连续多天重复同一家店或同一种招牌单品。")
        result.append("")

        for meal_type in ("breakfast", "lunch", "dinner"):
            restaurants = restaurants_by_meal.get(meal_type, [])
            result.append(f"{meal_titles.get(meal_type, meal_type)}:")
            if not restaurants:
                result.append("  暂无合适候选")
                result.append("")
                continue

            for i, restaurant in enumerate(restaurants[:5], 1):
                name = restaurant.get("name", "未知餐厅")
                address = restaurant.get("address", "地址未知")
                location = restaurant.get("location", {})
                longitude = location.get("longitude", "未知")
                latitude = location.get("latitude", "未知")
                category = restaurant.get("type", "分类未知")
                result.append(f"  {i}. {name}")
                result.append(f"     地址: {address}")
                result.append(f"     坐标: {longitude}, {latitude}")
                result.append(f"     分类: {category}")
            result.append("")

        return "\n".join(result)
