"""Trip planning orchestration built on autonomous tool-calling skills plus a single planner agent."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from typing import Any

from hello_agents import SimpleAgent

from ..models.schemas import Attraction, DayPlan, Hotel, Location, Meal, TripPlan, TripRequest, WeatherInfo
from ..services.amap_service import get_amap_service
from ..services.llm_service import get_llm
from ..skills import AttractionSkill, FoodSkill, HotelSkill, WeatherSkill
from ..utils.ttl_cache import TTLCache

_TRIP_PLAN_CACHE: TTLCache[tuple, TripPlan] = TTLCache(default_ttl_seconds=120, max_size=128)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PLANNER_AGENT_PROMPT = """你是行程规划专家，并且必须先使用工具补齐信息，再输出最终行程。

强制流程：
1. 第一轮必须至少调用 `attraction_search`、`weather_query`、`hotel_search`、`food_search` 这四个工具中的相关工具。
2. 如果你还没有拿到候选数据，禁止直接输出最终 JSON。
3. 只有在拿到工具结果之后，才允许输出最终 JSON。
4. 如果你需要调用工具，严格使用格式 `[TOOL_CALL:tool_name:key=value,key2=value2]`。
5. 不要解释工具调用，不要输出自然语言分析，拿到足够数据后直接输出 JSON。

字段约束：
1. `days[].attractions[]` 中每个景点都必须包含：`name`、`address`、`location`、`visit_duration`、`description`、`category`、`ticket_price`。
2. `days[].meals[]` 中每个餐食都必须使用字段：`type`、`name`、`address`、`description`、`estimated_cost`。不要使用 `meal_type`、`restaurant`、`dish`、`price` 这些字段名。
3. `weather_info[]` 中每条天气都必须使用字段：`date`、`day_weather`、`night_weather`、`day_temp`、`night_temp`、`wind_direction`、`wind_power`。
4. `hotel` 字段必须尽量复用酒店工具返回的候选。
5. 1-2 天优先同一家酒店；3 天及以上只有在景点明显跨城区或通勤成本过高时才更换酒店。
6. 避免连续多天重复同一家餐厅或同一种招牌单品，尤其不要把同一种特色早餐连续安排多天。

最终只返回完整 JSON，不要加 ```json 以外的解释说明。
"""


class TripPlannerOrchestrator:
    """Single orchestrator that delegates candidate fetching to autonomous tool-calling planner agent."""

    def __init__(self) -> None:
        print("Initializing trip planner orchestrator...")
        self.llm = get_llm()
        self.amap_service = get_amap_service()
        self.weather_skill = WeatherSkill()
        self.attraction_skill = AttractionSkill()
        self.hotel_skill = HotelSkill()
        self.food_skill = FoodSkill()
        self.planner_agent = SimpleAgent(
            name="行程规划专家",
            llm=self.llm,
            system_prompt=PLANNER_AGENT_PROMPT,
            max_tool_iterations=8,
        )
        self.planner_agent.add_tool(self.attraction_skill)
        self.planner_agent.add_tool(self.weather_skill)
        self.planner_agent.add_tool(self.hotel_skill)
        self.planner_agent.add_tool(self.food_skill)

    async def plan_trip(self, request: TripRequest) -> TripPlan:
        try:
            started_at = time.perf_counter()
            cache_key = (
                request.city,
                request.start_date,
                request.end_date,
                request.travel_days,
                request.transportation,
                request.accommodation,
                tuple(request.preferences or []),
                request.free_text_input or "",
            )
            cached_plan = _TRIP_PLAN_CACHE.get(cache_key)
            if cached_plan is not None:
                return cached_plan

            planner_query = self._build_planner_query(request)
            planner_response = await self._run_planner(planner_query)
            if not self._looks_like_usable_plan_response(planner_response):
                fallback_query = self._build_tool_enriched_query(request)
                planner_response = await self._run_planner(fallback_query)
            trip_plan = self._parse_response(planner_response, request)
            trip_plan = self._post_process_plan(trip_plan, request)
            _TRIP_PLAN_CACHE.set(cache_key, trip_plan, ttl_seconds=2 * 60)

            print(f"Trip plan generated in {time.perf_counter() - started_at:.2f}s")
            return trip_plan
        except Exception as exc:
            print(f"Trip planning failed: {exc}")
            return self._create_fallback_plan(request)

    async def _run_planner(self, planner_query: str) -> str:
        return await asyncio.to_thread(self.planner_agent.run, planner_query)

    def _looks_like_usable_plan_response(self, response: str) -> bool:
        if not response or "{" not in response:
            return False
        text = response.lower()
        weak_signals = [
            '"trip_request"',
            '"meal_type"',
            '"restaurant"',
            '"dish"',
        ]
        return not any(signal in text for signal in weak_signals)

    def get_runtime_status(self) -> dict[str, Any]:
        map_status = self.amap_service.get_runtime_status()
        return {
            "planner_name": self.planner_agent.name,
            "planner_tools_count": len(self.planner_agent.list_tools()),
            "skill_count": 4,
            "tool_calling_enabled": True,
            **map_status,
        }

    def _build_planner_query(self, request: TripRequest) -> str:
        payload = {
            "trip_request": {
                "city": request.city,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "travel_days": request.travel_days,
                "transportation": request.transportation,
                "accommodation": request.accommodation,
                "preferences": request.preferences,
                "free_text_input": request.free_text_input or "",
            },
            "first_step_mandatory_tool_calls": [
                f"[TOOL_CALL:attraction_search:city={request.city},keywords={request.preferences[0] if request.preferences else '景点'}]",
                f"[TOOL_CALL:weather_query:city={request.city}]",
                f"[TOOL_CALL:hotel_search:city={request.city},type={request.accommodation}]",
                f"[TOOL_CALL:food_search:city={request.city},preferences={','.join(request.preferences or [])}]",
            ],
            "output_schema_notes": {
                "meal_fields": ["type", "name", "address", "description", "estimated_cost"],
                "weather_fields": ["date", "day_weather", "night_weather", "day_temp", "night_temp", "wind_direction", "wind_power"],
                "attraction_fields": ["name", "address", "location", "visit_duration", "description", "category", "ticket_price"],
            },
        }
        return "先严格按 first_step_mandatory_tool_calls 调用工具，拿到结果后再输出最终 JSON。\n" + json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_tool_enriched_query(self, request: TripRequest) -> str:
        attraction_keywords = request.preferences[0] if request.preferences else "景点"
        direct_tool_results = {
            "attractions": self.attraction_skill.get_candidates(request.city, attraction_keywords, 10),
            "weather": self.weather_skill.get_candidates(request.city),
            "hotels": self.hotel_skill.get_candidates(request.city, request.accommodation, 6),
            "food": self.food_skill.get_candidates(request.city, "餐厅", "", request.preferences or []),
        }
        payload = {
            "trip_request": {
                "city": request.city,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "travel_days": request.travel_days,
                "transportation": request.transportation,
                "accommodation": request.accommodation,
                "preferences": request.preferences,
                "free_text_input": request.free_text_input or "",
            },
            "tool_results": direct_tool_results,
            "instruction": "你上一轮没有按要求产出可用结果。现在请直接基于 tool_results 输出符合 schema 的最终 JSON，不要输出分析，不要重复 trip_request 结构。",
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        try:
            json_str = self._extract_json_block(response)
            raw_data = json.loads(json_str)
            normalized = self._normalize_plan_payload(raw_data, request)
            return TripPlan(**normalized)
        except Exception as exc:
            print(f"Failed to parse planner response: {exc}")
            return self._create_fallback_plan(request)

    @staticmethod
    def _extract_json_block(response: str) -> str:
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            return response[start:end].strip()
        if "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            return response[start:end].strip()
        if "{" in response and "}" in response:
            start = response.find("{")
            end = response.rfind("}") + 1
            return response[start:end]
        raise ValueError("No JSON payload found in planner response")

    def _normalize_plan_payload(self, data: dict[str, Any], request: TripRequest) -> dict[str, Any]:
        data.setdefault("city", request.city)
        data.setdefault("start_date", request.start_date)
        data.setdefault("end_date", request.end_date)
        data.setdefault("overall_suggestions", "")
        data.setdefault("weather_info", [])

        for day_index, day in enumerate(data.get("days", [])):
            day.setdefault("date", (datetime.strptime(request.start_date, "%Y-%m-%d") + timedelta(days=day_index)).strftime("%Y-%m-%d"))
            day.setdefault("day_index", day_index)
            day.setdefault("description", f"第{day_index + 1}天行程")
            day.setdefault("transportation", request.transportation)
            day.setdefault("accommodation", request.accommodation)

            hotel = day.get("hotel") or {}
            if hotel:
                hotel.setdefault("address", "")
                hotel.setdefault("location", None)
                hotel.setdefault("price_range", "")
                hotel.setdefault("rating", "")
                hotel.setdefault("distance", "")
                hotel.setdefault("type", request.accommodation)
                hotel.setdefault("estimated_cost", 0)
                day["hotel"] = hotel

            normalized_attractions = []
            for item in day.get("attractions", []):
                normalized_attractions.append(
                    {
                        "name": item.get("name", "未命名景点"),
                        "address": item.get("address", f"{request.city}市区"),
                        "location": item.get("location") or {"longitude": 116.397128, "latitude": 39.916527},
                        "visit_duration": item.get("visit_duration") or item.get("duration") or 120,
                        "description": item.get("description") or item.get("intro") or f"{item.get('name', '景点')}游览点",
                        "category": item.get("category") or item.get("type") or "景点",
                        "ticket_price": item.get("ticket_price") or item.get("price") or 0,
                    }
                )
            day["attractions"] = normalized_attractions

            normalized_meals = []
            for item in day.get("meals", []):
                normalized_meals.append(
                    {
                        "type": item.get("type") or item.get("meal_type") or "meal",
                        "name": item.get("name") or item.get("restaurant") or "待补充餐厅",
                        "address": item.get("address"),
                        "location": item.get("location"),
                        "description": item.get("description") or item.get("dish") or "",
                        "estimated_cost": item.get("estimated_cost") or item.get("price") or 0,
                    }
                )
            day["meals"] = normalized_meals

        normalized_weather = []
        for item in data.get("weather_info", []):
            normalized_weather.append(
                {
                    "date": item.get("date", ""),
                    "day_weather": item.get("day_weather") or item.get("condition") or "",
                    "night_weather": item.get("night_weather") or item.get("condition") or "",
                    "day_temp": item.get("day_temp") or item.get("temperature") or 0,
                    "night_temp": item.get("night_temp") or item.get("temperature") or 0,
                    "wind_direction": item.get("wind_direction") or item.get("wind") or "",
                    "wind_power": item.get("wind_power") or item.get("wind") or "",
                }
            )
        data["weather_info"] = normalized_weather

        return data

    def _post_process_plan(self, trip_plan: TripPlan, request: TripRequest) -> TripPlan:
        self._fill_missing_hotels(trip_plan, request)
        self._fill_missing_meals(trip_plan, request)
        self._normalize_hotels(trip_plan, request)
        self._normalize_meals(trip_plan)
        return trip_plan

    def _fill_missing_hotels(self, trip_plan: TripPlan, request: TripRequest) -> None:
        hotel_candidates = self.hotel_skill.get_candidates(request.city, request.accommodation, 4)
        if not hotel_candidates:
            return
        default_hotel = Hotel(**hotel_candidates[0])
        for day in trip_plan.days:
            if day.hotel is None:
                day.hotel = Hotel(**default_hotel.model_dump())

    def _fill_missing_meals(self, trip_plan: TripPlan, request: TripRequest) -> None:
        candidates = self.food_skill.get_candidates(request.city, "餐厅", "", request.preferences or [])
        last_meal_name_by_type: dict[str, str] = {}
        for day in trip_plan.days:
            meal_map = {meal.type: meal for meal in day.meals}
            filled_meals: list[Meal] = []
            for meal_type in ("breakfast", "lunch", "dinner"):
                meal = meal_map.get(meal_type)
                if meal is None or "待补充" in meal.name:
                    meal = self._pick_meal_from_candidates(
                        meal_type,
                        candidates.get(meal_type, []),
                        avoid_name=last_meal_name_by_type.get(meal_type),
                    ) or Meal(type=meal_type, name=f"{meal_type}待补充", description="候选不足，建议到附近灵活选择")
                filled_meals.append(meal)
                last_meal_name_by_type[meal_type] = meal.name
            day.meals = filled_meals

    def _pick_meal_from_candidates(
        self,
        meal_type: str,
        candidates: list[dict[str, Any]],
        avoid_name: str | None = None,
    ) -> Meal | None:
        for item in candidates:
            if not item.get("name") or item.get("name") == avoid_name:
                continue
            return Meal(
                type=meal_type,
                name=item.get("name"),
                address=item.get("address"),
                location=Location(**item["location"]) if item.get("location") else None,
                description=item.get("type", ""),
                estimated_cost=30 if meal_type == "breakfast" else 60 if meal_type == "lunch" else 90,
            )
        return None

    def _normalize_hotels(self, trip_plan: TripPlan, request: TripRequest) -> None:
        if not trip_plan.days:
            return
        first_hotel = trip_plan.days[0].hotel
        if first_hotel is None:
            return
        keep_single_hotel = request.travel_days <= 2 or not self._has_large_cross_district_shift(trip_plan)
        if keep_single_hotel:
            for day in trip_plan.days:
                day.hotel = Hotel(**first_hotel.model_dump())

    def _has_large_cross_district_shift(self, trip_plan: TripPlan) -> bool:
        centers: list[tuple[float, float]] = []
        for day in trip_plan.days:
            coords = [
                (attr.location.longitude, attr.location.latitude)
                for attr in day.attractions
                if attr.location is not None
            ]
            if not coords:
                continue
            avg_lon = sum(item[0] for item in coords) / len(coords)
            avg_lat = sum(item[1] for item in coords) / len(coords)
            centers.append((avg_lon, avg_lat))
        if len(centers) < 2:
            return False
        first = centers[0]
        for current in centers[1:]:
            if abs(current[0] - first[0]) > 0.12 or abs(current[1] - first[1]) > 0.12:
                return True
        return False

    def _normalize_meals(self, trip_plan: TripPlan) -> None:
        last_meal_name_by_type: dict[str, str] = {}
        for day in trip_plan.days:
            normalized: list[Meal] = []
            meal_map = {meal.type: meal for meal in day.meals}
            for meal_type in ("breakfast", "lunch", "dinner"):
                meal = meal_map.get(meal_type)
                if meal is None:
                    meal = Meal(type=meal_type, name=f"{meal_type}待补充", description="候选不足，建议到附近灵活选择")
                elif meal.name == last_meal_name_by_type.get(meal_type):
                    meal = Meal(
                        type=meal_type,
                        name=f"{meal.name}（建议更换同类备选）",
                        address=meal.address,
                        location=meal.location,
                        description=meal.description,
                        estimated_cost=meal.estimated_cost,
                    )
                normalized.append(meal)
                last_meal_name_by_type[meal_type] = normalized[-1].name
            day.meals = normalized

    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        days: list[DayPlan] = []
        for day_index in range(request.travel_days):
            current_date = start_date + timedelta(days=day_index)
            attractions = [
                Attraction(
                    name=f"{request.city}景点{item_index + 1}",
                    address=f"{request.city}市区",
                    location=Location(
                        longitude=116.4 + day_index * 0.01 + item_index * 0.005,
                        latitude=39.9 + day_index * 0.01 + item_index * 0.005,
                    ),
                    visit_duration=120,
                    description=f"{request.city}的推荐景点",
                    category="景点",
                    ticket_price=30,
                )
                for item_index in range(2)
            ]
            meals = [
                Meal(type="breakfast", name=f"第{day_index + 1}天早餐", description="建议选择当地早餐店"),
                Meal(type="lunch", name=f"第{day_index + 1}天午餐", description="建议选择景点附近餐厅"),
                Meal(type="dinner", name=f"第{day_index + 1}天晚餐", description="建议选择本地特色餐厅"),
            ]
            days.append(
                DayPlan(
                    date=current_date.strftime("%Y-%m-%d"),
                    day_index=day_index,
                    description=f"第{day_index + 1}天行程",
                    transportation=request.transportation,
                    accommodation=request.accommodation,
                    attractions=attractions,
                    meals=meals,
                )
            )
        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为你生成的{request.city}{request.travel_days}日备用行程，建议出发前再次确认景点开放时间。",
        )


_trip_planner_orchestrator: TripPlannerOrchestrator | None = None


def get_trip_planner_agent() -> TripPlannerOrchestrator:
    global _trip_planner_orchestrator
    if _trip_planner_orchestrator is None:
        _trip_planner_orchestrator = TripPlannerOrchestrator()
    return _trip_planner_orchestrator
