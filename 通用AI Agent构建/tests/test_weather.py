import unittest

from yxbot.gateway import ToolCall
from yxbot.tools import run_tool
from yxbot.weather_cn import parse_aqi, parse_city_code, query_aqi


SEARCH = (
    '([{"ref":"101240101~jiangxi~南昌~Nanchang~南昌~Nanchang~791~330000~NC~江西"},'
    '{"ref":"101240103~jiangxi~南昌县~Nanchangxian~南昌县~Nanchangxian~791~330200~NCX~江西"}])'
)
AQI = (
    'setAirData({"name":"南昌","station":"101240101","data":['
    '{"time":"16","t1":"49","t2":"1","t3":"18","t4":"34","t5":"0.6","t6":"5","t7":"159","t8":"159","t9":"9"},'
    '{"time":"15","t1":"58","t2":"2","t3":"23","t4":"41","t5":"0.7","t6":"7","t7":"166","t8":"166","t9":"9"}'
    "]})"
)


class WeatherTests(unittest.TestCase):
    def test_parse_city_and_aqi(self):
        self.assertEqual(parse_city_code(SEARCH, "南昌市"), ("101240101", "南昌"))
        data = parse_aqi(AQI)
        self.assertEqual(data["name"], "南昌")

    def test_refuses_historical_date(self):
        text = query_aqi("南昌", "2020-01-01", fetch=lambda url: SEARCH)
        self.assertIn("不能查询 2020-01-01", text)
        self.assertIn("不要编造", text)

    def test_formats_today(self):
        def fetch(url):
            if "search" in url:
                return SEARCH
            return AQI

        text = query_aqi("南昌", None, fetch=fetch)
        self.assertIn("来源：中国天气网", text)
        self.assertIn("AQI 49", text)
        self.assertIn("优", text)
        self.assertNotIn("2020", text)

    def test_tool_returns_error_without_city(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            text = run_tool(Path(tmp), ToolCall("query_china_weather", {}))
            self.assertIn("缺少城市", text)


if __name__ == "__main__":
    unittest.main()
