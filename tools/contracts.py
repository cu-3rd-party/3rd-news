import json
from pathlib import Path

from lib.app import create_app
from lib.core.config import Settings
from thirdnews_contracts import ClassifyRequest, ClassifyResponse, NewsBatchRequest, NewsSubmission

ROOT = Path(__file__).resolve().parents[1]


def generate(*, check: bool) -> None:
    schemas = {
        "http/openapi.json": create_app(Settings()).openapi(),
        "http/news-submission.schema.json": NewsSubmission.model_json_schema(),
        "http/news-batch.schema.json": NewsBatchRequest.model_json_schema(),
        "classifier/request.schema.json": ClassifyRequest.model_json_schema(),
        "classifier/response.schema.json": ClassifyResponse.model_json_schema(),
    }
    for relative, schema in schemas.items():
        path = ROOT / "contracts" / relative
        if check:
            if json.loads(path.read_text()) != schema:
                raise SystemExit(f"Contract schema drift: {relative}")
        else:
            path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
    print(f"{'Verified' if check else 'Exported'} {len(schemas)} machine contracts")


def verify() -> None:
    generate(check=True)


def export() -> None:
    generate(check=False)
