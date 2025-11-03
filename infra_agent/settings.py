import logging
from enum import Enum
from typing import Optional, Union

from pydantic import AnyUrl, IPvAnyAddress, validator
from pydantic_settings import BaseSettings
from yarl import URL

logger = logging.getLogger(__name__)


def get_connection_string(
    uri: str, *, username: Optional[str] = None, password: Optional[str] = None, port: Optional[int] = None
):
    url = URL(uri).with_user(username).with_password(password)
    if port is not None:
        url = url.with_port(port)

    return url.human_repr()


class AmqpDsn(AnyUrl):
    allowed_schemes = {"amqp"}
    user_required = True


class Settings(BaseSettings):
    class LogLevel(Enum):
        DEBUG = "DEBUG"
        INFO = "INFO"
        WARN = "WARN"
        WARNING = "WARNING"
        ERROR = "ERROR"
        CRITICAL = "CRITICAL"

    DEBUG: bool = False
    HOST: Union[AnyUrl, IPvAnyAddress] = "0.0.0.0"
    PORT: int = 8080
    LOG_LEVEL: LogLevel = LogLevel.DEBUG
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    SSL_KEY_PATH: Optional[str] = None
    SSL_CERT_PATH: Optional[str] = None
    OPENAI_MODEL: str
    OPENAI_API_KEY: str
    OPENAI_API_URL: Union[AnyUrl, IPvAnyAddress] | None = None
    OPENAI_API_RATE_LIMIT_REQUESTS: int = 0
    OPENAI_API_RATE_LIMIT_TIMEWINDOW: int = 0
    GITLAB_URL: Union[AnyUrl, IPvAnyAddress] = "https://gitlab.com"
    GITLAB_TOKEN: str
    GITLAB_HELMFILE_PROJECT_PATH: str = "infrastructure/helmfile"
    GITLAB_WEBHOOK_PROMPT_FORMAT: str = """
{merge_request}
"""
    GITLAB_WEBHOOK_SYSTEM_PROMPT_FORMAT: str = """
You are an autonomous DevOps engineer responsible for managing GitLab repositories and ensuring CI/CD pipelines remain healthy.

BEHAVIOR RULES (important — follow exactly):
1. Before doing anything else, call the router tool named `route_intent` with two fields:
   - category: one of ["gitlab", "grafana", "kubernetes"]

2. After you call `route_intent`, STOP. Wait for the backend to load the tools for the chosen category. Do NOT attempt to call or simulate any other tools until you receive confirmation that the tools are loaded.

3. Once the tool group is loaded, continue reasoning and use available tools to gather information or perform actions. If a tool is available for an action, use it without asking for confirmation.

4. If you require a capability for which no tool exists, output exactly:
   MISSING FUNCTION: <short description of missing tool and why it's needed>
   and stop.

5. Always think step-by-step and include the minimal data the tools need as arguments.

Goal: analyze the merge request, its description, and diffs; then decide the best course of action to ensure pipelines are healthy. Use tools to inspect CI jobs, logs, pipeline status, and to apply fixes or merge when safe.
"""
    GITLAB_WEBHOOK_FOLLOWUP_PROMPT_FORMAT: str = """
You have received the GitLab merge request details and any prior tool outputs.

Follow these rules when you continue:
1. If, after using tools, the merge request is healthy and pipelines are passing, call the appropriate action tool (e.g., `approve_and_merge`) with the required parameters to approve and merge. Use the tool without asking for confirmation.

2. If pipelines are failing, use the available diagnostic and remediation tools to attempt fixes. After each remediation tool call, re-check pipeline status.

3. If you exhaust available actions and the issue remains or you need an unavailable capability, output:
   MISSING FUNCTION: <description of missing tool>
   and stop.

4. If the router returned category `unknown`, describe a single, minimal clarifying question the backend or user should answer (one short sentence) and stop.

5. When finished and the MR was merged or resolved, output a short final status line: either `MERGED` or `UNRESOLVED: <short reason>`.
"""
    GRAFANA_URL: Union[AnyUrl, IPvAnyAddress] = "0.0.0.0"
    GRAFANA_API_KEY: str
    GRAFANA_ORG_ID: int = 1
    GRAFANA_PROMETHEUS_DATASOURCE_NAME: str
    GRAFANA_WEBHOOK_SYSTEM_PROMPT_FORMAT: str = """
You are an autonomous Kubernetes expert responsible for cluster health. You received an alert from Grafana.

BEHAVIOR RULES (important — follow exactly):
1. Immediately call the router tool `route_intent` with:
- category: one of ["gitlab", "grafana", "kubernetes"]

2. Stop and wait for the backend to load tools for that category. Do NOT take actions or call tools until the backend confirms tools are loaded.

3. After tools are loaded, use available diagnostic and remediation tools to investigate and resolve the alert. Use action tools without additional confirmation.

4. If a necessary capability is missing, output exactly:
MISSING FUNCTION: <short description of missing tool>
and stop.

5. If the alert is resolved, output exactly `RESOLVED`. If it cannot be resolved with available tools, output `UNRESOLVED: <short reason>`.
"""
    GRAFANA_WEBHOOK_PROMPT_FORMAT: str = """
{alert_summaries}
"""
    GRAFANA_WEBHOOK_FOLLOWUP_PROMPT_FORMAT: str = """
Follow these rules:
1. If you resolve the alert using tools, output only:
   RESOLVED
   and nothing else.

2. If the alert cannot be resolved with available tools, output:
   UNRESOLVED: <concise reason>
   If missing tooling is required to proceed, output:
   MISSING FUNCTION: <short description>
   and stop.

3. If the router returned `unknown`, produce one minimal clarifying question for the backend/user and stop.

"""

    @validator("PORT")
    def validate_PORT(v):
        return int(v) if isinstance(v, str) else v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

logging.basicConfig(level=settings.LOG_LEVEL.value, format=settings.LOG_FORMAT)
