import logging
from typing import Dict, List

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

logger = logging.getLogger(__name__)


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


async def list_files_in_branch(branch: str, path: str = "") -> List[GitlabFile]:
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
    existing_files = [f.file_path for f in await list_files_in_branch("main")]
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


async def get_file_contents(branch: str, file_path: str = "") -> GitlabFile:
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


async def list_files_in_merge_request(merge_request_id: int) -> Dict[str, str]:
    """List files in repository for a given branch and path."""
    mr = await get_merge_request_details(merge_request_id)
    files = {}
    for f in await list_files_in_branch(mr.source_branch):
        gl_file = await get_file_contents(mr.source_branch)
        files[f.file_path] = gl_file.content
    return files


class GitlabMergeRequestFactory:
    def __init__(self):
        gl = gitlab.Gitlab(settings.GITLAB_URL, private_token=settings.GITLAB_TOKEN)
        self._project = gl.projects.get(settings.GITLAB_HELMFILE_PROJECT_PATH)
        self._source_branch = "main"
        self._mr_branch = None
        self._files = {}

    async def add_file_to_merge_request(self, file_path: str, file_contents: str):
        self._files[file_path] = file_contents

    async def create_commit_in_branch(self, branch_name: str, commit_message: str):
        new_branch = True
        try:
            self._project.branches.create({"branch": branch_name, "ref": self._source_branch})
            logger.info(f"Branch '{branch_name}' created from '{self._source_branch}'")
        except Exception:
            new_branch = False
            logger.info(f"Branch '{branch_name}' already exists")

        existing_files = []
        for f in self._project.repository_tree(ref=self._source_branch, all=True, recursive=True):
            path = f.get("path", None)
            if path and path not in existing_files:
                existing_files.append(path)
        if not new_branch:
            for f in self._project.repository_tree(ref=branch_name, all=True, recursive=True):
                path = f.get("path", None)
                if path and path not in existing_files:
                    existing_files.append(path)

        commit_actions = []
        for file_path, file_contents in self._files.items():
            commit_actions.append(
                {
                    "action": "update" if file_path in existing_files else "create",
                    "file_path": file_path,
                    "content": file_contents,
                }
            )
        commit = self._project.commits.create(
            {"branch": branch_name, "commit_message": commit_message, "actions": commit_actions}
        )
        logger.info(f"Commit created: {commit.id}")
        self._mr_branch = branch_name

    async def create_merge_request(self, title: str, description: str):
        mr = self._project.mergerequests.create(
            {
                "source_branch": self._mr_branch,
                "target_branch": self._source_branch,
                "title": title,
                "description": description,
                "remove_source_branch": True,
            }
        )

        logger.info(f"created: {mr.web_url}")


# if __name__ == '__main__':

#     import asyncio

#     async def main():
#         test = GitlabMergeRequestFactory()
#         await test.add_file_to_merge_request("testfile.txt", "simpletest")
#         await test.create_commit_in_branch("test14", 'test commit')
#         await test.create_merge_request('TEST title', "some desription")

#     asyncio.run(main())
