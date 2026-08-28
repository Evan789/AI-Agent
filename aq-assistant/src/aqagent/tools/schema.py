"""Frozen tool JSON Schema for eval and DeepSeek prompts. Stage 1 subset."""

TOOL_SCHEMAS = {
    "echo": {
        "name": "echo",
        "description": "Echo text. Only for connectivity tests, never for diagnosis.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    "list_analyzers": {
        "name": "list_analyzers",
        "description": "List the 11 air-quality diagnosis analyzers (id, Chinese name, desc). Use when the user asks what methods exist.",
        "parameters": {"type": "object", "properties": {}},
    },
    "ask_user": {
        "name": "ask_user",
        "description": (
            "Ask the user to fill missing slots. Required when intent is analyze "
            "but city/period/file are missing. Do not call run_analysis without slots."
        ),
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    "run_analysis": {
        "name": "run_analysis",
        "description": (
            "Run one or more diagnosis analyzers (never assume all 11). "
            "Pass analyzers as a list of ids. Use all 11 only when the user asks for "
            "a full episode diagnosis. Requires city+dates or a local data file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "analyzers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Analyzer ids to run. Subset of the 11. Empty/all = full suite.",
                },
                "data": {"type": "string"},
                "reuse_dirs": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        },
    },
    "load_episode": {
        "name": "load_episode",
        "description": "Load summaries from the last episode without running analyzers. Use for recap follow-ups.",
        "parameters": {
            "type": "object",
            "properties": {
                "reuse_dirs": {"type": "array", "items": {"type": "string"}},
                "analyzers": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

STAGE_TOOL_NAMES = ["echo", "list_analyzers", "ask_user", "run_analysis", "load_episode"]
STAGE1_TOOL_NAMES = STAGE_TOOL_NAMES
