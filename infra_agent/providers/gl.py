from typing import List

import gitlab

from infra_agent.models.generic import PromptToolError
from infra_agent.models.gl import (
    GitlabCommit,
    GitlabFile,
    GitlabMergeRequest,
    GitlabMergeRequestList,
)
from infra_agent.settings import settings

gl = gitlab.Gitlab(str(settings.GITLAB_URL), private_token=settings.GITLAB_TOKEN)


async def list_opened_merge_requests() -> GitlabMergeRequestList:
    """List opened merge requests for a project."""
    project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
    mrs = project.mergerequests.list(state="opened", all=True)
    items = [
        GitlabMergeRequest(
            id=mr.id,
            title=mr.title,
            description=mr.description,
            state=mr.state,
            target_branch=mr.target_branch,
            source_branch=mr.source_branch,
        )
        for mr in mrs
    ]
    return GitlabMergeRequestList(items=items)


async def get_merge_request_details(mr_id: int) -> GitlabMergeRequest:
    """Get details of a merge request."""
    project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
    mr = project.mergerequests.get(mr_id)
    return GitlabMergeRequest(
        id=mr.id,
        title=mr.title,
        description=mr.description,
        state=mr.state,
        target_branch=mr.target_branch,
        source_branch=mr.source_branch,
    )


async def update_file_and_push(branch: str, file_path: str, content: str, commit_message: str) -> GitlabCommit:
    """Update a file in a branch and push."""
    project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
    file = project.files.get(file_path=file_path, ref=branch)
    file.content = content
    file.save(branch=branch, commit_message=commit_message)
    commit = project.commits.list(ref_name=branch, per_page=1)[0]
    return GitlabCommit(
        id=commit.id,
        short_id=commit.short_id,
        title=commit.title,
        message=commit.message,
        author_name=commit.author_name,
        author_email=commit.author_email,
        authored_date=commit.authored_date,
        committer_name=commit.committer_name,
        committer_email=commit.committer_email,
        committed_date=commit.committed_date,
        parent_ids=commit.parent_ids,
        web_url=commit.web_url,
    )


async def create_merge_request_from_branch(
    source_branch: str, target_branch: str, title: str, description: str
) -> GitlabMergeRequest:
    """Create a merge request from a branch."""
    project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
    mr = project.mergerequests.create(
        {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
        }
    )
    return GitlabMergeRequest(
        id=mr.id,
        title=mr.title,
        description=mr.description,
        target_branch=mr.target_branch,
        source_branch=mr.source_branch,
    )


async def create_merge_request(
    merge_request_branch: str, commit_message: str, title: str, description: str, files_updated: dict[str, str]
):
    if not files_updated:
        raise PromptToolError(
            message="Missing or empty `file_contents` parameter! you MUST provide map of filepath/filecontents here!",
            tool_name="create_merge_request",
            inputs={
                "merge_request_branch": merge_request_branch,
                "commit_message": commit_message,
                "title": title,
                "description": description,
                "files_updated": files_updated,
            },
        )
    mr_target_branch_name = "main"
    project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
    existing_files = [f.file_path for f in await list_files_in_repository("main")]
    commit_actions = []
    for file_path, file_contents in files_updated.items():
        commit_actions.append(
            {
                "action": "update" if file_path in existing_files else "create",
                "file_path": file_path,
                "content": file_contents,
            }
        )
    try:
        project.commits.create(
            {
                "commit_message": commit_message,
                "author_email": "ai",
                "author_name": "ai",
                "actions": commit_actions,
                "branch": merge_request_branch,
                "start_branch": mr_target_branch_name,
            }
        )
    except Exception as e:
        raise PromptToolError(
            message=f"Problem creating commit! {e}",
            tool_name="create_merge_request",
            inputs={
                "merge_request_branch": merge_request_branch,
                "commit_message": commit_message,
                "title": title,
                "description": description,
                "files_updated": files_updated,
            },
        )

    try:
        project.mergerequests.create(
            {
                "source_branch": merge_request_branch,
                "target_branch": mr_target_branch_name,
                "title": title,
                "description": description,
                "labels": "ai,automerge",
            }
        )
    except Exception as e:
        raise PromptToolError(
            message=f"Problem creating merge request from commit! {e}",
            tool_name="create_merge_request",
            inputs={
                "merge_request_branch": merge_request_branch,
                "commit_message": commit_message,
                "title": title,
                "description": description,
                "files_updated": files_updated,
            },
        )


async def approve_merge_request(mr_id: int) -> bool:
    """Approve a merge request."""
    project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
    mr = project.mergerequests.get(mr_id)
    mr.approve()
    return True


async def get_file_contents(branch: str, file_path: str) -> GitlabFile:
    """Get file contents from repository, branch, and path."""
    project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
    file = project.files.get(file_path=file_path, ref=branch)
    return GitlabFile(
        file_path=file.file_path,
        file_name=file.file_name,
        size=file.size,
        encoding=file.encoding,
        content=file.decode().decode("utf8"),
        ref=branch,
        blob_id=getattr(file, "blob_id", None),
        commit_id=getattr(file, "commit_id", None),
        last_commit_id=getattr(file, "last_commit_id", None),
        execute_filemode=getattr(file, "execute_filemode", None),
    )


async def list_files_in_repository(branch: str, path: str = "") -> List[GitlabFile]:
    """List files in repository for a given branch and path."""
    project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
    files = project.repository_tree(path=path, ref=branch, all=True, recursive=True)
    result = []
    for f in files:
        result.append(
            GitlabFile(
                file_path=f.get("path", ""),
                file_name=f.get("name", ""),
                size=f.get("size", None),
                encoding=None,
                content=None,
                ref=branch,
                blob_id=f.get("id", None),
                commit_id=None,
                last_commit_id=None,
                execute_filemode=f.get("mode", None) == "100755",
            )
        )
    return result


class GitlabMergeRequestFactory:
    def __init__(self):
        self.__last_merge_request = None
        self.__last_merge_request_file_list = {}

    async def start_merge_request(self, title: str, description: str):
        self.__last_merge_request = GitlabMergeRequest(
            title=title, description=description, target_branch="main", source_branch="ai-test"
        )

    async def add_file_to_merge_request(self, file_path: str, file_contents: str):
        if not self.__last_merge_request:
            raise PromptToolError(
                message="It's not possible to add files to merge request if it's not created yet! run `start_merge_request` tool with `title` and `description` parameters first!",
                inputs={"file_path": file_path, "file_contents": file_contents},
                tool_name="add_file_to_merge_request",
            )
        self.__last_merge_request_file_list[file_path] = file_contents

    async def commit_and_push_merge_request(self, commit_message: str):
        if not self.__last_merge_request:
            raise PromptToolError(
                message="It's not possible to add files to merge request if it's not created yet! run `start_merge_request` tool with `title` and `description` parameters first!",
                inputs={"commit_message": commit_message},
                tool_name="commit_and_push_merge_request",
            )
        if not self.__last_merge_request_file_list:
            raise PromptToolError(
                message="It's not possible to push empty merge request if it's not created yet! run `start_merge_request` tool with `title` and `description` parameters first, then add file updates using `add_file_to_merge_request` tool!",
                inputs={"commit_message": commit_message},
                tool_name="commit_and_push_merge_request",
            )

        project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
        existing_files = [f.file_path for f in await list_files_in_repository(self.__last_merge_request.source_branch)]
        commit_actions = []
        for file_path, file_contents in self.__last_merge_request_file_list.items():
            commit_actions.append(
                {
                    "action": "update" if file_path in existing_files else "create",
                    "file_path": file_path,
                    "content": file_contents,
                }
            )
        try:
            project.commits.create(
                {
                    "commit_message": commit_message,
                    "author_email": "ai",
                    "author_name": "ai",
                    "actions": commit_actions,
                    "branch": self.__last_merge_request.target_branch,
                    "start_branch": self.__last_merge_request.source_branch,
                }
            )
        except Exception as e:
            raise PromptToolError(
                message=f"Problem creating commit! {e}",
                tool_name="create_merge_request",
                inputs={
                    "commit_message": commit_message,
                },
            )

        try:
            project.mergerequests.create(
                {
                    "source_branch": self.__last_merge_request.target_branch,
                    "target_branch": self.__last_merge_request.source_branch,
                    "title": self.__last_merge_request.title,
                    "description": self.__last_merge_request.description,
                    "labels": "ai,automerge",
                }
            )
        except Exception as e:
            raise PromptToolError(
                message=f"Problem creating merge request from commit! {e}",
                tool_name="create_merge_request",
                inputs={
                    "commit_message": commit_message,
                },
            )
        self.__last_merge_request_file_list = {}
