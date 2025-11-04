from datetime import datetime
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field, HttpUrl


class AlertLabels(BaseModel):
    alertname: str
    team: str
    zone: str


class Alert(BaseModel):
    status: str
    labels: dict[str, str]
    annotations: dict[str, str]
    startsAt: datetime
    endsAt: datetime
    generatorURL: HttpUrl
    fingerprint: str
    silenceURL: HttpUrl
    dashboardURL: HttpUrl | None = None
    panelURL: HttpUrl | None = None
    values: Dict[str, float] = Field(default_factory=dict)


class GrafanaAlertsSumary(BaseModel):
    description: str | None = None
    summary: str | None = None
    labels: Dict[str, str] | None = None
    values: Dict[str, float] | None = None


class GrafanaWebhookPayload(BaseModel):
    receiver: str
    status: str
    orgId: int
    alerts: List[Alert]
    groupLabels: Dict[str, str] = Field(default_factory=dict)
    commonLabels: Dict[str, str]
    commonAnnotations: Dict[str, str] = Field(default_factory=dict)
    externalURL: HttpUrl
    version: str
    groupKey: str
    truncatedAlerts: int
    title: str
    state: str
    message: str

    async def summary(self) -> List[dict]:
        return [
            GrafanaAlertsSumary(
                description=alert.annotations.get("description", ""),
                summary=alert.annotations.get("summary", ""),
                values=alert.values,
                labels=alert.labels,
            ).model_dump(exclude_none=True)
            for alert in self.alerts
        ]


class GrafanaDatasource(BaseModel):
    id: int
    uid: str
    orgId: int
    name: str
    type: str


class GrafanaPrometheusQueryResultData(BaseModel):
    metric: dict[str, str]
    values: List[Tuple[int, float]]


class GrafanaPrometheusQueryResult(BaseModel):
    resultType: str
    result: List[GrafanaPrometheusQueryResultData]


class GrafanaPrometheusDatapoints(BaseModel):
    datapoints: dict[int, float]


class GrafanaPrometheusQueryOutput(BaseModel):
    status: str
    data: GrafanaPrometheusQueryResult


class GrafanaAlertList(BaseModel):
    alerts: List[Alert]
