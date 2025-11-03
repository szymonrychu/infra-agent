from typing import List

from infra_agent.models.ai import (
    OpenAIFunction,
    OpenAITool,
    OpenAIToolParameter,
    OpenAIToolParameterProperty,
)
from infra_agent.models.generic import PromptToolError
from infra_agent.providers.gl import (
    approve_merge_request,
    create_merge_request_from_branch,
    get_file_contents,
    get_merge_request_details,
    list_files_in_repository,
    list_opened_merge_requests,
    update_file_and_push,
)
from infra_agent.providers.grafana import (
    get_node_cpu_usage,
    get_node_memory_usage,
    get_pod_container_cpu_usage,
    get_pod_container_memory_usage,
    list_grafana_alerts,
)
from infra_agent.providers.k8s import (
    delete_pod,
    get_node_resources,
    get_pod_details,
    get_pod_helm_release_metadata,
    get_pod_logs,
    list_namespaces,
    list_node_pods,
    list_nodes,
    list_pod_containers,
    list_pods_by_namespace,
)

_route_to_tool_list = {
    "gitlab": [
        OpenAITool(
            function=OpenAIFunction(
                name="list_opened_merge_requests",
                description="List opened merge requests in Gitlab project consisting of Helmfile based Helm releases",
            ),
            handler=list_opened_merge_requests,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="get_merge_request_details",
                description="Get details of a specific merge request by its ID",
                parameters=OpenAIToolParameter(
                    properties={"mr_id": OpenAIToolParameterProperty(description="Merge request id", type="integer")},
                    required=["mr_id"],
                ),
            ),
            handler=get_merge_request_details,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="update_file_and_push",
                description="Update a file in a branch and push the changes",
                parameters=OpenAIToolParameter(
                    properties={
                        "branch": OpenAIToolParameterProperty(description="Name of the branch to update"),
                        "file_path": OpenAIToolParameterProperty(description="Path to the file to update"),
                        "content": OpenAIToolParameterProperty(description="New content for the file"),
                        "commit_message": OpenAIToolParameterProperty(description="Commit message for the update"),
                    },
                    required=["branch", "file_path", "content", "commit_message"],
                ),
            ),
            handler=update_file_and_push,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="create_merge_request_from_branch",
                description="Create a merge request from a branch to the default branch",
                parameters=OpenAIToolParameter(
                    properties={
                        "source_branch": OpenAIToolParameterProperty(description="Name of the source branch"),
                        "target_branch": OpenAIToolParameterProperty(description="Name of the target branch"),
                        "title": OpenAIToolParameterProperty(description="Title of the merge request"),
                        "description": OpenAIToolParameterProperty(description="Description of the merge request"),
                    },
                    required=["source_branch", "target_branch", "title", "description"],
                ),
            ),
            handler=create_merge_request_from_branch,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="approve_merge_request",
                description="Approve a merge request by its ID",
                parameters=OpenAIToolParameter(
                    properties={"mr_id": OpenAIToolParameterProperty(description="Merge request id", type="integer")},
                    required=["mr_id"],
                ),
            ),
            handler=approve_merge_request,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="get_file_contents",
                description="Get file contents from repository, branch, and path",
                parameters=OpenAIToolParameter(
                    properties={
                        "branch": OpenAIToolParameterProperty(description="Branch name"),
                        "file_path": OpenAIToolParameterProperty(description="Path to the file in the repository"),
                    },
                    required=["branch", "file_path"],
                ),
            ),
            handler=get_file_contents,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="list_files_in_repository",
                description="List files in a repository at a specific branch and path",
                parameters=OpenAIToolParameter(
                    properties={
                        "branch": OpenAIToolParameterProperty(description="Branch name"),
                        "path": OpenAIToolParameterProperty(description="Path in the repository to list files from"),
                    },
                    required=["branch"],
                ),
            ),
            handler=list_files_in_repository,
        ),
    ],
    "grafana": [
        OpenAITool(
            function=OpenAIFunction(
                name="get_pod_container_cpu_usage",
                description="Get Kubernetes pod container cpu usage from Prometheus- returns dict(timestamp, datapoint)",
                parameters=OpenAIToolParameter(
                    properties={
                        "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                        "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                        "container_name": OpenAIToolParameterProperty(description="Pod's container name"),
                        # "from_s": OpenAIToolParameterProperty(
                        #     description="Starting epoch time for Prometheus query", type="integer"
                        # ),
                        # "to_s": OpenAIToolParameterProperty(
                        #     description="Ending epoch time for Prometheus query (defaults to current timestamp)",
                        #     type="integer",
                        # ),
                        # "steps": OpenAIToolParameterProperty(
                        #     description="Amount to steps to get between to_s and from_s (defaults to step every 60s)",
                        #     type="integer",
                        # ),
                    },
                    required=["namespace", "pod_name", "container_name"],
                ),
            ),
            handler=get_pod_container_cpu_usage,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="get_pod_container_memory_usage",
                description="Get Kubernetes pod container memory usage from Prometheus- returns dict(timestamp, datapoint)",
                parameters=OpenAIToolParameter(
                    properties={
                        "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                        "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                        "container_name": OpenAIToolParameterProperty(description="Pod's container name"),
                        # "from_s": OpenAIToolParameterProperty(
                        #     description="Starting epoch time for Prometheus query", type="integer"
                        # ),
                        # "to_s": OpenAIToolParameterProperty(
                        #     description="Ending epoch time for Prometheus query (defaults to current timestamp)",
                        #     type="integer",
                        # ),
                        # "steps": OpenAIToolParameterProperty(
                        #     description="Amount to steps to get between to_s and from_s (defaults to step every 60s)",
                        #     type="integer",
                        # ),
                    },
                    required=["namespace", "pod_name", "container_name"],
                ),
            ),
            handler=get_pod_container_memory_usage,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="get_node_cpu_usage",
                description="Get node cpu usage from Prometheus- returns dict(timestamp, datapoint)",
                parameters=OpenAIToolParameter(
                    properties={
                        "node_name": OpenAIToolParameterProperty(description="Node name"),
                        # "from_s": OpenAIToolParameterProperty(
                        #     description="Starting epoch time for Prometheus query", type="integer"
                        # ),
                        # "to_s": OpenAIToolParameterProperty(
                        #     description="Ending epoch time for Prometheus query (defaults to current timestamp)",
                        #     type="integer",
                        # ),
                        # "steps": OpenAIToolParameterProperty(
                        #     description="Amount to steps to get between to_s and from_s (defaults to step every 60s)",
                        #     type="integer",
                        # ),
                    },
                    required=["node_name"],
                ),
            ),
            handler=get_node_cpu_usage,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="get_node_memory_usage",
                description="Get node memory usage from Prometheus- returns dict(timestamp, datapoint)",
                parameters=OpenAIToolParameter(
                    properties={
                        "node_name": OpenAIToolParameterProperty(description="Node name"),
                        # "from_s": OpenAIToolParameterProperty(
                        #     description="Starting epoch time for Prometheus query", type="integer"
                        # ),
                        # "to_s": OpenAIToolParameterProperty(
                        #     description="Ending epoch time for Prometheus query (defaults to current timestamp)",
                        #     type="integer",
                        # ),
                        # "steps": OpenAIToolParameterProperty(
                        #     description="Amount to steps to get between to_s and from_s (defaults to step every 60s)"
                        # ),
                    },
                    required=["node_name"],
                ),
            ),
            handler=get_node_memory_usage,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="list_grafana_alerts",
                description="Get list of current Grafana alerts",
            ),
            handler=list_grafana_alerts,
        ),
    ],
    "kubernetes": [
        OpenAITool(
            function=OpenAIFunction(
                name="get_pod_logs",
                description="Get Kubernetes pod container logs",
                parameters=OpenAIToolParameter(
                    properties={
                        "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                        "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                        "container_name": OpenAIToolParameterProperty(description="Pod's container name "),
                        # "tail_lines": OpenAIToolParameterProperty(type="integer", description="How many lines to get"),
                    },
                    required=["namespace", "pod_name", "container_name"],
                ),
            ),
            handler=get_pod_logs,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="list_pods_by_namespace",
                description="List Kubernetes pods",
                parameters=OpenAIToolParameter(
                    properties={"namespace": OpenAIToolParameterProperty(description="Pod namespace")},
                    required=["namespace"],
                ),
            ),
            handler=list_pods_by_namespace,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="delete_pod",
                description="Delete specified pod",
                parameters=OpenAIToolParameter(
                    properties={
                        "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                        "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                    },
                    required=["namespace", "pod_name"],
                ),
            ),
            handler=delete_pod,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="get_pod_details",
                description="Gets pod spec and status details",
                parameters=OpenAIToolParameter(
                    properties={
                        "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                        "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                    },
                    required=["namespace", "pod_name"],
                ),
            ),
            handler=get_pod_details,
        ),
        OpenAITool(
            function=OpenAIFunction(name="list_namespaces", description="List all Kubernetes namespaces"),
            handler=list_namespaces,
        ),
        OpenAITool(
            function=OpenAIFunction(name="list_nodes", description="List all Kubernetes nodes"), handler=list_nodes
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="list_pod_containers",
                description="List all containers within a pod",
                parameters=OpenAIToolParameter(
                    properties={
                        "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                        "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                    },
                    required=["namespace", "pod_name"],
                ),
            ),
            handler=list_pod_containers,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="list_node_pods",
                description="Get Kubernetes pod resources and limits",
                parameters=OpenAIToolParameter(
                    properties={"node_name": OpenAIToolParameterProperty(description="Node name")},
                    required=["node_name"],
                ),
            ),
            handler=list_node_pods,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="get_node_resources",
                description="Get Kubernetes node resource capacity and possible allocatablity",
                parameters=OpenAIToolParameter(
                    properties={"node_name": OpenAIToolParameterProperty(description="Node name")},
                    required=["node_name"],
                ),
            ),
            handler=get_node_resources,
        ),
        OpenAITool(
            function=OpenAIFunction(
                name="get_pod_helm_release_metadata",
                description="Gets latest Helm release metadata for a given pod",
                parameters=OpenAIToolParameter(
                    properties={
                        "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                        "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                    },
                    required=["namespace", "pod_name"],
                ),
            ),
            handler=get_pod_helm_release_metadata,
        ),
    ],
}


async def _router_tool(category: str) -> List[OpenAITool]:
    if category not in _route_to_tool_list.keys():
        raise PromptToolError(
            message="No such category found",
            tool_name="route_tools",
            inputs={
                "category": category,
            },
        )
    return _route_to_tool_list.get(category, [])


router = OpenAITool(
    function=OpenAIFunction(
        name="route_tools",
        description="Main router tool to select category of tools to use",
        parameters=OpenAIToolParameter(
            description="Category of the tools to route to",
            properties={
                "category": OpenAIToolParameterProperty(
                    description="Pod namespace", enum=["gitlab", "grafana", "kubernetes"]
                )
            },
            required=["category"],
        ),
    ),
    handler=_router_tool,
)
