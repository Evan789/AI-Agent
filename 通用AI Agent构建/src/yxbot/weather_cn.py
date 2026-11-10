"""Read-only China Weather (weather.com.cn) air-quality lookup."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))
LEVELS = {
    "1": "优",
    "2": "良",
    "3": "轻度污染",
    "4": "中度污染",
    "5": "重度污染",
    "6": "严重污染",
}


class WeatherError(Exception):
    pass


def today_cn() -> date:
    return datetime.now(CN_TZ).date()


def _fetch(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "YXBot/0.1",
            "Referer": "http://www.weather.com.cn/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise WeatherError(f"中国天气网暂时取不到数据：{exc}") from exc


def parse_city_code(payload: str, city: str) -> tuple[str, str]:
    start = payload.find("[")
    end = payload.rfind("]")
    if start < 0 or end <= start:
        raise WeatherError(f"没有找到城市：{city}")
    try:
        rows = json.loads(payload[start : end + 1])
    except json.JSONDecodeError as exc:
        raise WeatherError(f"没有找到城市：{city}") from exc
    wanted = city.strip().removesuffix("市")
    matches: list[tuple[str, str]] = []
    for row in rows:
        parts = str(row.get("ref") or "").split("~")
        if len(parts) < 3:
            continue
        code, name = parts[0], parts[2]
        if len(code) == 9 and code.isdigit() and name in {wanted, city.strip()}:
            matches.append((code, name))
    if not matches:
        raise WeatherError(f"没有找到城市：{city}")
    return matches[0]


def parse_aqi(payload: str) -> dict:
    start = payload.find("{")
    end = payload.rfind("}")
    if start < 0 or end <= start:
        raise WeatherError("空气质量数据无法解析")
    try:
        data = json.loads(payload[start : end + 1])
    except json.JSONDecodeError as exc:
        raise WeatherError("空气质量数据无法解析") from exc
    if not isinstance(data, dict) or not data.get("data"):
        raise WeatherError("空气质量数据为空")
    return data


def _format_hour(row: dict) -> str:
    level = LEVELS.get(str(row.get("t2") or ""), "未知")
    return (
        f"{row.get('time')}时 AQI {row.get('t1')}（{level}）"
        f" PM2.5 {row.get('t3')} PM10 {row.get('t4')}"
        f" SO2 {row.get('t9')} NO2 {row.get('t6')} O3 {row.get('t7')} CO {row.get('t5')}"
    )


def query_aqi(city: str, day: str | None = None, fetch=_fetch) -> str:
    name = (city or "").strip()
    if not name:
        raise WeatherError("缺少城市")
    today = today_cn()
    if day:
        try:
            asked = datetime.strptime(day.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise WeatherError("日期格式应为 YYYY-MM-DD") from exc
        if asked != today:
            return (
                f"中国天气网这个只读接口只有当天逐小时空气质量，不能查询 {asked.isoformat()}。"
                f"今天是 {today.isoformat()}。没有历史数字，不要编造。"
            )
    code, matched = parse_city_code(
        fetch("http://toy1.weather.com.cn/search?cityname=" + urllib.parse.quote(name)),
        name,
    )
    data = parse_aqi(fetch(f"https://d1.weather.com.cn/aqi_all/{code}.html"))
    rows = list(data.get("data") or [])
    recent = rows[:6]
    lines = [
        "来源：中国天气网（只读）",
        f"城市：{data.get('name') or matched}（{code}）",
        f"日期：{today.isoformat()} 当天逐小时，不是历史回查",
        "字段：AQI，PM2.5，PM10，SO2，NO2，O3（1小时），CO",
        "最近时次：",
    ]
    lines.extend(_format_hour(row) for row in recent)
    return "\n".join(lines)
