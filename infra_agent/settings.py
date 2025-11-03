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
    GITLAB_WEBHOOK_PROMPT_FORMAT: str = "{merge_request}"
    GITLAB_WEBHOOK_SYSTEM_PROMPT_FORMAT: str = """
You are a autonomous DevOps engineer, managing Gitlab repositories and making sure CI/CD pipelines are
healthy.
You received a webhook event from Gitlab regarding a merge request, please analyze it, it's description and changes
and decide the best course of action to ensure the pipelines are healthy.
In case you need more information to proceed, use the available tools to get it.
If you need to perform an action, use the available tools to do so.
Always think step by step.
"""
    GITLAB_WEBHOOK_FOLLOWUP_PROMPT_FORMAT: str = """
If the merge request can be considered as healthy and pipelines are passing answer use provided tool to approve and merge it.
If not please get back to reasoning and try to use provided actions to fix the problems.
If there is a tool provided for something, use it without asking form confirmation.
to get more informations that are necessary to continue reasoning or resolve the problem.
If there is any spefic tool missing answer "MISSING FUNCTION: <description of missing tool>".
"""
    GRAFANA_URL: Union[AnyUrl, IPvAnyAddress] = "0.0.0.0"
    GRAFANA_API_KEY: str
    GRAFANA_ORG_ID: int = 1
    GRAFANA_PROMETHEUS_DATASOURCE_NAME: str
    GRAFANA_WEBHOOK_SYSTEM_PROMPT_FORMAT: str = """
You are a autonomous Kubernetes expert, managing Kubernetes cluster and making sure it's alive.
You received an alert from Grafana.
Analyze the alert and decide the best course of action to resolve the issue.
In case you need more information to proceed, use the available tools to get it.
If you need to perform an action, use the available tools to do so.
Always think step by step.
"""
    GRAFANA_WEBHOOK_PROMPT_FORMAT: str = """
{alert_summaries}
"""
    GRAFANA_WEBHOOK_FOLLOWUP_PROMPT_FORMAT: str = """
If the solution was provided and alert can be considered as resolved answer "RESOLVED" and avoid any other comments or formatting.
Otherwise, get back to reasoning and try to use provided actions.
If there is a tool provided for something, use it without asking form confirmation.
to get more informations that are necessary to continue reasoning or resolve the problem.
If there is any spefic tool missing answer "MISSING FUNCTION: <description of missing tool>".
"""

    @validator("PORT")
    def validate_PORT(v):
        return int(v) if isinstance(v, str) else v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

logging.basicConfig(level=settings.LOG_LEVEL.value, format=settings.LOG_FORMAT)
