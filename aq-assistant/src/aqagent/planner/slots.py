"""Rule slot filling + analyzer selection."""

from __future__ import annotations

import re

from aqagent.constants import ANALYZER_IDS, ANALYZERS, MECHANISM_TO_ANALYZERS

_CITY_RE = re.compile(
    r"(南昌县|南昌|九江|上饶|抚州|宜春|吉安|赣州|景德镇|萍乡|新余|鹰潭|"
    r"鄱阳湖|鄱阳|井冈山|瑞金|进贤|安义|孝感|武汉|长沙|北京|上海|广州|深圳|杭州)"
)
_DATE_RE = re.compile(r"(\d{4})[-\/年](\d{1,2})[-\/月](\d{1,2})?日?")
_LIST_RE = re.compile(r"分析器|方法清单|有哪些方法|都有哪些|skill\b", re.I)
_ANALYZE_RE = re.compile(r"分析(?!器)|诊断|污染过程|形势|为什么|怎么管")
_PLOT_RE = re.compile(r"画图|画一个图|出图|趋势图|变化趋势|折线图|把图")
_ALL_RE = re.compile(r"全部分析器|所有分析器|全面|完整诊断|该数据")
_FOLLOW_RE = re.compile(r"那[么]?|刚才|再看|还看|接着|上次|这个结果|同样时段")


def is_followup(text: str) -> bool:
    return bool(_FOLLOW_RE.search(text or ""))


def is_subset_pick(analyzers: list[str]) -> bool:
    return bool(analyzers) and list(analyzers) != list(ANALYZER_IDS)


def parse_slots(text: str) -> dict:
    t = (text or "").strip()
    city_m = _CITY_RE.search(t)
    dates: list[str] = []
    for m in _DATE_RE.finditer(t):
        if len(dates) >= 2:
            break
        y, mo, d = m.group(1), m.group(2), m.group(3) or "01"
        dates.append(f"{y}-{mo.zfill(2)}-{d.zfill(2)}")
    start = dates[0] if dates else None
    end = dates[1] if len(dates) >= 2 else (dates[0] if dates else None)
    analyzers = select_analyzers(t)
    plot = bool(_PLOT_RE.search(t))
    intent = "chat"
    if _LIST_RE.search(t) and not re.search(r"分析该|诊断该|污染过程", t):
        intent = "list"
    elif plot and not _ANALYZE_RE.search(t):
        intent = "plot"
    elif _ANALYZE_RE.search(t) or analyzers or is_followup(t):
        intent = "analyze"
    return {
        "intent": intent,
        "city": city_m.group(1) if city_m else None,
        "start": start,
        "end": end,
        "analyzers": analyzers,
        "followup": is_followup(t),
        "raw": t,
    }


def select_analyzers(text: str) -> list[str]:
    """Pick a subset. Empty means 'not specified' (caller may default to all)."""
    t = text or ""
    low = t.lower()
    picked: list[str] = []

    for a in ANALYZERS:
        if a["id"] in low and a["id"] not in picked:
            picked.append(a["id"])
    for a in sorted(ANALYZERS, key=lambda x: len(x["name"]), reverse=True):
        if a["name"] in t and a["id"] not in picked:
            picked.append(a["id"])
    for key, ids in sorted(MECHANISM_TO_ANALYZERS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if key.lower() in low:
            for i in ids:
                if i not in picked:
                    picked.append(i)
    if picked:
        return picked
    if _ALL_RE.search(t) or parse_slots_intent_all(t):
        return list(ANALYZER_IDS)
    return []


def parse_slots_intent_all(text: str) -> bool:
    return bool(_ANALYZE_RE.search(text or ""))


def parse_skill_flag(raw: str | None) -> list[str] | None:
    """CLI --skill all | id | id,id. None means do not override NL selection."""
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    if text.lower() == "all":
        return list(ANALYZER_IDS)
    parts = [p.strip() for p in text.split(",") if p.strip()]
    return parts


def normalize_analyzer_ids(raw) -> tuple[list[str], str | None]:
    """Return (ids, error). Rejects unknown ids. Empty raw → all 11."""
    if raw is None or raw == "" or raw == []:
        return list(ANALYZER_IDS), None
    if isinstance(raw, str):
        if raw.strip().lower() == "all":
            return list(ANALYZER_IDS), None
        items = [p.strip() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        return [], f"analyzers 类型无效: {type(raw).__name__}"
    if not items:
        return list(ANALYZER_IDS), None
    unknown = [i for i in items if i not in ANALYZER_IDS]
    if unknown:
        return [], f"未知分析器: {', '.join(unknown)}。可用: {', '.join(ANALYZER_IDS)}"
    # keep order, drop dupes
    out: list[str] = []
    for i in items:
        if i not in out:
            out.append(i)
    return out, None
