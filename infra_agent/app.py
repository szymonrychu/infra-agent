import json
import logging

from fastapi import Depends, FastAPI, Request, Response

from infra_agent.models.grafana import GrafanaWebhookPayload
from infra_agent.settings import settings
from infra_agent.workers.ai import gpt_query


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        path = ""
        if record.args and isinstance(record.args, dict):
            path = record.args.get("path", "")
        elif record.args and isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2] if isinstance(record.args[2], str) else ""
        return path not in ("/healthz/live", "/healthz/ready")


logger = logging.getLogger("uvicorn.access")
logger.addFilter(EndpointFilter())

app = FastAPI()


async def get_body(request: Request):
    bytes = await request.body()
    return bytes.decode("utf-8")


@app.get("/healthz/live")
async def liveness() -> Response:
    return Response("{}", status_code=200)


@app.get("/healthz/ready")
async def readiness() -> Response:
    return Response("{}", status_code=200)


@app.post("/webhooks/grafana")
async def grafana_webhook(payload: GrafanaWebhookPayload) -> Response:
    alert_summaries = await payload.summary()

    prompt = settings.GRAFANA_WEBHOOK_PROMPT_FORMAT
    system_prompt = settings.GRAFANA_WEBHOOK_SYSTEM_PROMPT_FORMAT

    messages = []
    result = await gpt_query(
        prompt,
        system_prompt,
        messages,
        model=settings.OPENAI_MODEL,
        alert_summaries=alert_summaries,
    )

    return Response(
        json.dumps(result.model_dump(exclude_none=True)),
        media_type="application/json",
        status_code=200,
    )


if settings.DEBUG:

    @app.post("/debug")
    def input_request(data: str = Depends(get_body)):
        print(data)
        return Response("{}", status_code=200)
