import logging
from enum import Enum
from ipaddress import IPv4Address
from typing import Optional, Union

from httpx import URL
from pydantic import AnyUrl, IPvAnyAddress
from pydantic_settings import BaseSettings
from yarl import URL as connURL

logger = logging.getLogger(__name__)


def get_connection_string(
    uri: str, *, username: Optional[str] = None, password: Optional[str] = None, port: Optional[int] = None
):
    url = connURL(uri).with_user(username).with_password(password)
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
    HOST: Union[AnyUrl, IPvAnyAddress] = IPv4Address("0.0.0.0")
    PORT: int = 8080
    LOG_LEVEL: LogLevel = LogLevel.DEBUG
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    OPENAI_MODEL: str = "gpt-5-nano"
    OPENAI_API_KEY: str = ""
    OPENAI_API_URL: Union[str, URL] | None = None
    OPENAI_API_RATE_LIMIT_REQUESTS: int = 0
    OPENAI_API_RATE_LIMIT_TIMEWINDOW: int = 0
    GITLAB_URL: Union[str, URL] = "https://gitlab.com"
    GITLAB_TOKEN: str = ""
    GITLAB_HELMFILE_PROJECT_PATH: str = "szymonrychu/helmfile"
    GRAFANA_URL: Union[AnyUrl, IPvAnyAddress] = IPv4Address("0.0.0.0")
    GRAFANA_API_KEY: str = ""
    GRAFANA_ORG_ID: int = 1
    GRAFANA_PROMETHEUS_DATASOURCE_NAME: str = "prometheus"
    GRAFANA_WEBHOOK_SYSTEM_PROMPT_FORMAT: str = """
You are an autonomous Kubernetes expert responsible for maintaining cluster health and stability.
You have access to a set of diagnostic and remediation tools.
You receive alerts from Grafana and must investigate, reason, and fix the underlying problem.
Don't hasitate to update related configuration- use `get_pod_helm_release_metadata` to obtain current
configuration from cluster and repository, use `create_merge_request` to commit, push and create merge-request.
Important: NEVER provide updates to files you didn't receive from `get_pod_helm_release_metadata` function!
If it's possible create merge request optimizing configuration.

BEHAVIOR RULES (critical — follow precisely):

1. Always think step-by-step and reason logically about the problem before calling any tool.

2. Use only the tools that are currently available to you.
   - Never invent, simulate, or describe tool behavior.
   - Never output plain JSON, lists of intended actions, or multiple tool calls in one message.
   - Call exactly one tool at a time using the standard structured tool call interface:
     {{
       "name": "<tool_name>",
       "arguments": {{"<param1>": "...", "<param2>": "..." }}
     }}

3. Before calling any tool, verify in your reasoning whether the same tool was already executed with identical parameters.
   - If it was, do not repeat it unless you have a clear justification (e.g., new data, context change).
   - If a resource (namespace, pod, container) does not exist or is unreachable, do not query it again.

4. Do not fabricate arguments.
   - If a required parameter value is unknown, use available tools to discover it.
   - If no available tool can obtain it, note it in reasoning and continue with what you can verify.
   - Never insert placeholders like “unknown”, “parameter-unknown”, or “node-unknown”.

5. Use tools iteratively:
   - Gather minimal necessary information.
   - Analyze it in reasoning.
   - Apply fixes or escalate to next diagnostic steps.
   - Continue until the alert is understood and resolved or all reasonable options are exhausted.

6. Never ask the user for confirmation or data.
   You are fully autonomous — fix the issue with the tools you have.

7. Once you have resolved the issue or exhausted all available reasoning paths, call the `{finish_function_name}` tool **exactly once**.

   Required fields:
   - solved (boolean): true if the alert has been resolved, false otherwise.
   - explanation (string): short explanation (1–3 sentences) of what was found and what actions were taken.
   - missing_tools (optional array of strings): tools that would have helped resolve the case faster or more effectively.

   Output format:
   → Return this as a structured tool call, not plain text or markdown.

8. Example {finish_function_name} call:
   {{
     "name": "{finish_function_name}",
     "arguments": {{
       "solved": true,
       "explanation": "Pod restart policy corrected; alert cleared.",
       "missing_tools": []
     }}
   }}

Follow these rules exactly. You are operating autonomously — do not output commentary or summaries outside of reasoning or tool calls.
"""
    GRAFANA_WEBHOOK_PROMPT_FORMAT: str = """
You received the following Grafana alert(s):

{alert_summaries}

Begin by analyzing what they indicate about cluster state and what information you need next.
"""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

logging.basicConfig(level=settings.LOG_LEVEL.value, format=settings.LOG_FORMAT)
