from typing import Any

PROMPT_VERSION = "2.0.0"
SCHEMA_VERSION = "2.0.0"
SYSTEM_PROMPT = """Классифицируй новость только по переданной схеме. Верни JSON,
соответствующий response_format. Не придумывай оси или значения. Evidence должно
содержать короткий фрагмент текста, который подтверждает каждую метку. Корневой
объект имеет единственное поле labels. Каждый элемент labels содержит ровно поля
axis, value, confidence, reason и evidence."""
RESPONSE_SCHEMA: dict[str, Any] = {
    "name": "thirdnews_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "axis": {"type": "string"},
                        "value": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["axis", "value", "confidence", "reason", "evidence"],
                },
            }
        },
        "required": ["labels"],
    },
}
