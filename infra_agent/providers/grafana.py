import time
from enum import Enum
from typing import List

import aiohttp

from infra_agent.models.generic import PromptToolError
from infra_agent.models.grafana import (
    GrafanaDatasource,
    GrafanaNumericResult,
    GrafanaPrometheusQueryOutput,
)
from infra_agent.settings import settings

__grafana_api_headers = {
    "Authorization": f"Bearer {settings.GRAFANA_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


async def __get_datasource_id() -> int | None:
    url = f"{settings.GRAFANA_URL}api/datasources"

    datasources = []
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=__grafana_api_headers) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Query failed: {resp.status} {text}")
            datasources = [GrafanaDatasource(**d) for d in await resp.json()]

    for datasource in datasources:
        if (
            datasource.uid == settings.GRAFANA_PROMETHEUS_DATASOURCE_NAME
            and datasource.org_id == settings.GRAFANA_ORG_ID
        ):
            return datasource.id
    return None


async def __query_prometheus_range(promql: str, from_s: int, to_s: int) -> GrafanaPrometheusQueryOutput:
    datasource_id = await __get_datasource_id()
    step = await __get_step(from_s, to_s)

    url = (
        f"{settings.GRAFANA_URL}api/datasources/proxy/{datasource_id}/api/v1/query_range"
        f"?query={promql}&start={from_s}&end={to_s}&step={step}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=__grafana_api_headers) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Query failed: {resp.status} {text}")
            d = await resp.json()
            return GrafanaPrometheusQueryOutput.model_validate(d)


class QueryType(Enum):
    min = "min"
    avg = "avg"
    max = "max"

    @staticmethod
    def values() -> List[str]:
        return [t.value for t in QueryType]


async def _min_avg_max_over_time_query(
    q_type: QueryType, metric: str, hours: int, unit: str | None = None
) -> GrafanaNumericResult:
    to_s = round(time.time())
    from_s = round(time.time()) - hours * 60 * 60
    promql = f"{q_type}_over_time({metric}[{hours}h:])"
    res = await __query_prometheus_range(promql, from_s, to_s)
    _, datapoint = res.data.result[0].values[0]
    return GrafanaNumericResult(result=datapoint, unit=unit)


async def __get_step(from_s: int, to_s: int) -> str:
    diff_s = to_s - from_s
    diff_h = float(diff_s) / 60.0 / 60.0
    if diff_h < 1:
        return "1m"
    elif diff_h < 6:
        return "2m"
    elif diff_h < 24:
        return "5m"
    else:
        return "10m"


async def get_node_cpu_usage(
    node_name: str, from_s: int | None = None, to_s: int | None = None
) -> GrafanaPrometheusQueryOutput:
    if not to_s:
        to_s = round(time.time())
    if not from_s or from_s == 0:
        from_s = to_s - 60 * 60
    step = await __get_step(from_s, to_s)
    promql = f'((1 - sum without (mode) (rate(node_cpu_seconds_total{{job="node-exporter", mode=~"idle|iowait|steal", instance="{node_name}"}}[{step}])))/ignoring(cpu) group_left count without (cpu, mode) (node_cpu_seconds_total{{job="node-exporter", mode="idle", instance="{node_name}"}}))'
    try:
        return await __query_prometheus_range(promql, from_s, to_s)
    except Exception:
        raise PromptToolError(
            message="Failed to query Prometheus for pod container CPU usage",
            tool_name="get_node_cpu_usage",
            inputs={
                "node_name": node_name,
                "from_s": from_s,
                "to_s": to_s,
            },
        )


async def get_node_memory_usage(
    node_name: str, from_s: int | None = None, to_s: int | None = None
) -> GrafanaPrometheusQueryOutput:
    if not to_s:
        to_s = round(time.time())
    if not from_s or from_s == 0:
        from_s = to_s - 60 * 60
    promql = f'(node_memory_MemTotal_bytes{{job="node-exporter", instance="{node_name}"}}-node_memory_MemFree_bytes{{job="node-exporter", instance="{node_name}"}}-node_memory_Buffers_bytes{{job="node-exporter", instance="{node_name}"}}-node_memory_Cached_bytes{{job="node-exporter", instance="{node_name}"}})'
    try:
        return await __query_prometheus_range(promql, from_s, to_s)
    except Exception:
        raise PromptToolError(
            message="Failed to query Prometheus for pod container CPU usage",
            tool_name="get_node_memory_usage",
            inputs={"node_name": node_name, "from_s": from_s, "to_s": to_s},
        )


# def _hours_ago_epoch(hours: float, from_dt:datetime|None = None) -> int:
#     """Return epoch milliseconds minus given hours from a datetime or current time.

#     Args:
#         hours: Number of hours to subtract (can be fractional)
#         from_dt: Optional datetime to subtract from (defaults to current time)

#     Returns:
#         Epoch timestamp in milliseconds
#     """
#     if from_dt is None:
#         from_dt = datetime.now()
#     ts = from_dt.timestamp() - (hours * 3600)
#     return int(round(ts * 1000))

# async def list_grafana_alerts(firing:bool=True, resolved:bool=False, hours_history:float = 100) -> List[GrafanaAlertInstance]:
#     """List alerts from Grafana API."""
#     url = f"{settings.GRAFANA_URL}api/annotations?from={_hours_ago_epoch(hours_history)}&type=alert&limit=1000"
#     async with aiohttp.ClientSession() as session:
#         async with session.get(url, headers=__grafana_api_headers) as resp:
#             content = await resp.text()
#             if resp.status != 200:
#                 raise PromptToolError(
#                     message="Failed to list grafana alerts",
#                     tool_name="get_node_memory_usage",
#                     inputs={},
#                 )
#             alerts_data = await resp.json()
#             alerts = []
#             for alert_instance in [GrafanaAlertInstance.model_validate(a) for a in alerts_data if a]:
#                 if firing and alert_instance.new_state == 'Alerting':
#                         alerts.append(alert_instance)
#                 if resolved and alert_instance.new_state == 'Normal':
#                         alerts.append(alert_instance)
#             return alerts


async def get_cpu_usage_over(
    query_type: QueryType, hours: int, namespace: str, pod_name: str, container_name: str
) -> GrafanaNumericResult:
    metric = f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}", pod="{pod_name}", container="{container_name}"}}[5m])'
    return await _min_avg_max_over_time_query(query_type, metric, hours, "cpu")


async def get_memory_usage_over(
    query_type: QueryType, hours: int, namespace: str, pod_name: str, container_name: str
) -> GrafanaNumericResult:
    metric = f'container_memory_usage_bytes{{namespace="{namespace}", pod="{pod_name}", container="{container_name}"}}'
    ret = await _min_avg_max_over_time_query(query_type, metric, hours, "mb")
    ret.result = round(ret.result / 1024 / 1024)
    return ret
