from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from infra_agent.models.generic import InfraAgentBaseModel


class Alert(InfraAgentBaseModel):
    # status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    # starts_at: datetime = Field(alias="startsAt")
    # ends_at: datetime = Field(alias="endsAt")
    # can be a relative query string like "?orgId=1"
    # silence_url: str = Field(alias="silenceURL")
    # dashboard_url: Optional[str] = Field(None, alias="dashboardURL")
    # panel_url: Optional[str] = Field(None, alias="panelURL")
    values: Dict[str, Any] = Field(default_factory=dict)


class GrafanaWebhookPayload(InfraAgentBaseModel):
    receiver: str
    status: str
    # org_id: int = Field(alias="orgId")
    alerts: List[Alert]
    group_labels: Dict[str, str] = Field(default_factory=dict, alias="groupLabels")
    common_labels: Dict[str, str] = Field(alias="commonLabels")
    common_annotations: Dict[str, str] = Field(default_factory=dict, alias="commonAnnotations")
    # external_url: HttpUrl = Field(alias="externalURL")
    # version: str
    # group_key: str = Field(alias="groupKey")
    # truncated_alerts: int = Field(alias="truncatedAlerts")
    title: str
    # state: str
    message: str


class GrafanaDatasource(InfraAgentBaseModel):
    id: int
    uid: str
    org_id: int = Field(alias="orgId")
    name: str
    type: str


class GrafanaPrometheusQueryResultData(InfraAgentBaseModel):
    metric: dict[str, str]
    values: List[Tuple[int, float]]


class GrafanaPrometheusQueryResult(InfraAgentBaseModel):
    result_type: str = Field(alias="resultType")
    result: List[GrafanaPrometheusQueryResultData]


class GrafanaPrometheusDatapoints(InfraAgentBaseModel):
    datapoints: dict[int, float]


class GrafanaPrometheusQueryOutput(InfraAgentBaseModel):
    status: str
    data: GrafanaPrometheusQueryResult


class GrafanaAlertInstanceData(InfraAgentBaseModel):
    """Container for the `data` field returned by Grafana alert instance APIs."""

    values: Dict[str, float] | None = Field(default=None)
    no_data: Optional[bool] = Field(False, alias="noData")


class GrafanaAlertInstance(InfraAgentBaseModel):
    """Model for Grafana runtime alert instance (e.g. response from /api/ruler/...).

    Matches payloads like:
    {"id":5824,"alertId":6,"alertName":"Kube Node not ready",...,"data":{"values":{"A":1,...}}}
    """

    id: int
    alert_id: int = Field(alias="alertId")
    alert_name: str = Field(alias="alertName")
    dashboard_id: int = Field(alias="dashboardId")
    dashboard_uid: Optional[str] = Field("", alias="dashboardUID")
    panel_id: int = Field(alias="panelId")
    user_id: int = Field(alias="userId")
    new_state: str = Field(alias="newState")
    prev_state: str = Field(alias="prevState")
    created: int  # epoch ms
    updated: int  # epoch ms
    time: int  # epoch ms
    time_end: int = Field(alias="timeEnd")  # epoch ms
    text: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    login: Optional[str] = Field("", alias="login")
    email: Optional[str] = Field("", alias="email")
    avatar_url: Optional[str] = Field("", alias="avatarUrl")
    data: Optional[GrafanaAlertInstanceData] | None = None


class _RelativeTimeRange(InfraAgentBaseModel):
    # JSON uses the key "from" which is a Python keyword, so alias it
    from_: int = Field(alias="from")
    to: int


class _RuleDataModel(InfraAgentBaseModel):
    """Flexible container for the per-query `model` field in alert rules.

    Grafana's `model` is different between query types; make a permissive
    model that defines the common fields we expect but allows extras.
    """

    editor_mode: Optional[str] = Field(None, alias="editorMode")
    expr: Optional[str] = None
    instant: Optional[bool] = None
    interval_ms: Optional[int] = Field(None, alias="intervalMs")
    legend_format: Optional[str] = Field(None, alias="legendFormat")
    max_data_points: Optional[int] = Field(None, alias="maxDataPoints")
    range: Optional[bool] = None
    ref_id: Optional[str] = Field(None, alias="refId")
    # fields used by expression/reduce/math models
    conditions: Optional[List[Dict[str, Any]]] = None
    datasource: Optional[Dict[str, Any]] = None
    expression: Optional[str] = None
    reducer: Optional[str] = None
    type: Optional[str] = None
    hide: Optional[bool] = None

    class Config:
        extra = "allow"


class _RuleDataItem(InfraAgentBaseModel):
    ref_id: str = Field(alias="refId")
    query_type: str = Field(alias="queryType")
    relative_time_range: _RelativeTimeRange = Field(alias="relativeTimeRange")
    datasource_uid: str = Field(alias="datasourceUid")
    model: _RuleDataModel


class GrafanaProvisioningAlertRule(InfraAgentBaseModel):
    id: int
    uid: str
    # Grafana uses "orgID" (capital D) in this API
    org_id: int = Field(alias="orgID")
    folder_uid: str = Field(alias="folderUID")
    rule_group: str = Field(alias="ruleGroup")
    title: str
    condition: str
    data: List[_RuleDataItem]
    updated: Optional[datetime] = None
    no_data_state: Optional[str] = Field(None, alias="noDataState")
    exec_err_state: Optional[str] = Field(None, alias="execErrState")
    # "for" is a reserved word in Python; alias to for_
    for_: Optional[str] = Field(None, alias="for")
    keep_firing_for: Optional[str] = None
    annotations: Optional[Dict[str, str]] = None
    provenance: Optional[str] = None
    is_paused: Optional[bool] = Field(None, alias="isPaused")
    notification_settings: Optional[Any] = None
    record: Optional[Any] = None


class GrafanaNumericResult(InfraAgentBaseModel):
    result: float
    unit: str | None = None
