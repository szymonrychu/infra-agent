from typing import List, Optional

import gitlab

from infra_agent.models.generic import InfraAgentBaseModel
from infra_agent.settings import settings

gl = gitlab.Gitlab(str(settings.GITLAB_URL), private_token=settings.GITLAB_TOKEN)


class GitlabMergeRequest(InfraAgentBaseModel):
    id: int | None = None
    title: str
    state: str = "opened"
    description: str
    target_branch: str
    source_branch: str


class GitlabMergeRequestList(InfraAgentBaseModel):
    """List of Gitlab merge requests"""

    items: List[GitlabMergeRequest]


class GitlabWebhookPayload(InfraAgentBaseModel):
    object_kind: str
    user: dict
    project: dict
    object_attributes: GitlabMergeRequest


class GitlabCommit(InfraAgentBaseModel):
    id: str
    short_id: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    authored_date: Optional[str] = None
    committer_name: Optional[str] = None
    committer_email: Optional[str] = None
    committed_date: Optional[str] = None
    parent_ids: Optional[List[str]] = None
    web_url: Optional[str] = None


class GitlabRepository(InfraAgentBaseModel):
    id: int
    name: str
    description: Optional[str] = None
    web_url: Optional[str] = None
    url: Optional[str] = None
    visibility: Optional[str] = None
    default_branch: Optional[str] = None
    created_at: Optional[str] = None
    last_activity_at: Optional[str] = None


class GitlabFile(InfraAgentBaseModel):
    file_path: str
    file_name: str
    size: Optional[int] = None
    encoding: Optional[str] = None
    content: Optional[str] = None
    ref: Optional[str] = None
    blob_id: Optional[str] = None
    commit_id: Optional[str] = None
    last_commit_id: Optional[str] = None
    execute_filemode: Optional[bool] = None
