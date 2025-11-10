from typing import List

from infra_agent.models.ai import (
    OpenAICaseSummary,
    OpenAIFunction,
    OpenAITool,
    OpenAIToolParameter,
    OpenAIToolParameterProperty,
    OpenAIToolParameterPropertyItems,
)
from infra_agent.models.generic import PromptToolError
from infra_agent.providers.gl import (
    GitlabMergeRequestFactory,
    list_files_in_merge_request,
    list_opened_merge_requests,
)
from infra_agent.providers.grafana import (
    QueryType,
    get_cpu_usage_over,
    get_memory_usage_over,
    get_node_cpu_usage,
    get_node_memory_usage,
)
from infra_agent.providers.k8s import (
    get_helm_release_definition,
    get_node_details,
    get_node_resources,
    get_pod_container_logs,
    get_pod_details,
    list_containers_in_pod,
    list_namespaces,
    list_nodes,
    list_pods_in_namespace,
    list_pods_in_node,
)

_merge_request_factory = GitlabMergeRequestFactory()


async def _closer_tool(
    solved: bool,
    explanation: str,
    missing_tools: List[str] | None = None,
) -> OpenAICaseSummary:
    if not explanation:
        raise PromptToolError(
            message="Not possible to close conversation without meaningful explanation and conversation summary!",
            tool_name="finish",
            inputs={
                "solved": solved,
                "explanation": explanation,
                "missing_tools": missing_tools,
            },
        )
    return OpenAICaseSummary(
        solved=solved,
        explanation=explanation,
        missing_tools=missing_tools or [],
    )


closer = OpenAITool(
    function=OpenAIFunction(
        name="finish",
        description="Run the function to finish the case and provide final answer to the user.",
        parameters=OpenAIToolParameter(
            properties={
                "solved": OpenAIToolParameterProperty(
                    description="Information for user if the case was solved successfully",
                    type="boolean",
                ),
                "explanation": OpenAIToolParameterProperty(
                    description="Explanation message for the user about the case resolution",
                    type="string",
                ),
                "missing_tools": OpenAIToolParameterProperty(
                    description="List of tools that would be useful to solve the case, but are not available",
                    type="array",
                    items=OpenAIToolParameterPropertyItems(type="string"),
                ),
            },
            required=["solved", "explanation"],
        ),
    ),
    handler=_closer_tool,
)

tools = [
    closer,
    OpenAITool(
        function=OpenAIFunction(
            name="get_pod_container_logs",
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
        handler=get_pod_container_logs,
    ),
    OpenAITool(
        function=OpenAIFunction(
            name="list_pods_in_namespace",
            description="List Kubernetes pods",
            parameters=OpenAIToolParameter(
                properties={"namespace": OpenAIToolParameterProperty(description="Pod namespace")},
                required=["namespace"],
            ),
        ),
        handler=list_pods_in_namespace,
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
    OpenAITool(function=OpenAIFunction(name="list_nodes", description="List all Kubernetes nodes"), handler=list_nodes),
    OpenAITool(
        function=OpenAIFunction(
            name="get_node_details",
            description="Get details about node in Kubernetes",
            parameters=OpenAIToolParameter(
                properties={
                    "node_name": OpenAIToolParameterProperty(description="Node name"),
                    "include_labels": OpenAIToolParameterProperty(
                        description="Flag whether to include node labels (enable only if needed)", type="boolean"
                    ),
                    "include_annotations": OpenAIToolParameterProperty(
                        description="Flag whether to include node annotations (enable only if needed)", type="boolean"
                    ),
                },
                required=["node_name"],
            ),
        ),
        handler=get_node_details,
    ),
    OpenAITool(
        function=OpenAIFunction(
            name="list_containers_in_pod",
            description="List all containers within a pod",
            parameters=OpenAIToolParameter(
                properties={
                    "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                    "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                },
                required=["namespace", "pod_name"],
            ),
        ),
        handler=list_containers_in_pod,
    ),
    OpenAITool(
        function=OpenAIFunction(
            name="list_pods_in_node",
            description="Get Kubernetes pod resources and limits",
            parameters=OpenAIToolParameter(
                properties={"node_name": OpenAIToolParameterProperty(description="Node name")},
                required=["node_name"],
            ),
        ),
        handler=list_pods_in_node,
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
            description="Gets latest Helm release metadata along with default and override values.yaml files used in repository to customize the release",
            parameters=OpenAIToolParameter(
                properties={
                    "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                    "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                },
                required=["namespace", "pod_name"],
            ),
        ),
        handler=get_helm_release_definition,
    ),
    OpenAITool(
        function=OpenAIFunction(
            name="get_cpu_usage_over",
            description="Allows to get min/avg/max container CPU usage in CPUs over given time in hours from now",
            parameters=OpenAIToolParameter(
                properties={
                    "query_type": OpenAIToolParameterProperty(description="Pod namespace", enum=QueryType.values()),
                    "hours": OpenAIToolParameterProperty(description="Pod namespace", type="integer"),
                    "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                    "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                    "container_name": OpenAIToolParameterProperty(description="Pod's container name"),
                },
                required=["query_type", "hours", "namespace", "pod_name", "container_name"],
            ),
        ),
        handler=get_cpu_usage_over,
    ),
    OpenAITool(
        function=OpenAIFunction(
            name="get_memory_usage_over",
            description="Allows to get min/avg/max container memory usage in MBs over given time in hours from now",
            parameters=OpenAIToolParameter(
                properties={
                    "query_type": OpenAIToolParameterProperty(description="Pod namespace", enum=QueryType.values()),
                    "hours": OpenAIToolParameterProperty(description="Pod namespace", type="integer"),
                    "namespace": OpenAIToolParameterProperty(description="Pod namespace"),
                    "pod_name": OpenAIToolParameterProperty(description="Pod name"),
                    "container_name": OpenAIToolParameterProperty(description="Pod's container name"),
                },
                required=["query_type", "hours", "namespace", "pod_name", "container_name"],
            ),
        ),
        handler=get_memory_usage_over,
    ),
    OpenAITool(
        function=OpenAIFunction(
            name="get_node_cpu_usage_from_grafana",
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
            name="get_node_memory_usage_from_grafana",
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
    # OpenAITool(
    #     function=OpenAIFunction(
    #         name="list_alerts_in_grafana",
    #         description="Get list of current Grafana alerts",
    #     ),
    #     handler=list_grafana_alerts,
    # ),
    # OpenAITool(
    #     function=OpenAIFunction(
    #         name="create_merge_request",
    #         description="Commits file updates into repository and creates merge requests from them",
    #         parameters=OpenAIToolParameter(
    #             properties={
    #                 "merge_request_branch": OpenAIToolParameterProperty(description="branch for merge request"),
    #                 "commit_message": OpenAIToolParameterProperty(description="meaningful commit message (use semantic commits)"),
    #                 "title": OpenAIToolParameterProperty(description="Title of the merge request (use semantic commits)"),
    #                 "description": OpenAIToolParameterProperty(description="Meaninful description of the merge request along with data and reasoning backing it up"),
    #                 "files_updated": OpenAIToolParameterProperty(
    #                     type = 'object',
    #                     description = 'dict, where key is filepath and value contains file contents that should be updated in the merge request. Do NOT pass empty objects or arrays.',
    #                     additional_properties = { "type": "string" },
    #                     min_properties = 1
    #                 )
    #             },
    #             required=["merge_request_branch", "commit_message", "title", "description", "files_updated"],
    #         ),
    #     ),
    #     handler=create_merge_request,
    # ),
    OpenAITool(
        function=OpenAIFunction(description="Lists all opened merge requests", name="list_opened_merge_requests"),
        handler=list_opened_merge_requests,
    ),
    OpenAITool(
        function=OpenAIFunction(
            description="Lists all opened merge requests",
            name="list_files_in_merge_request",
            parameters=OpenAIToolParameter(
                properties={
                    "merge_request_id": OpenAIToolParameterProperty(
                        description="Merge request id (one from the list provided by `list_opened_merge_requests` tool)",
                        type="integer",
                    ),
                },
                required=["merge_request_id"],
            ),
        ),
        handler=list_files_in_merge_request,
    ),
    OpenAITool(
        function=OpenAIFunction(
            description="Allows to add file update to merge request. Can be run multiple times to add multiple files in one commit. IMPORTANT! Never guess file contents or their paths, use `get_pod_helm_release_metadata` to read current configuration!",
            name="add_file_to_merge_request",
            parameters=OpenAIToolParameter(
                properties={
                    "file_path": OpenAIToolParameterProperty(description="Path of the file, that gets updated"),
                    "file_contents": OpenAIToolParameterProperty(
                        description="New contents of the file thats being updated. IMPORTANT! Must contain the whole file after edits!"
                    ),
                },
                required=["file_path", "file_contents"],
            ),
        ),
        handler=_merge_request_factory.add_file_to_merge_request,
    ),
    OpenAITool(
        function=OpenAIFunction(
            description="Pushes previously added files as commit. IMPORTANT: `create_commit_in_branch` tool must be run after running `add_file_to_merge_request`",
            name="create_commit_in_branch",
            parameters=OpenAIToolParameter(
                properties={
                    "branch_name": OpenAIToolParameterProperty(
                        description="Name of the branch to commit to. IMPORTANT: Use the same branch for all changes you do"
                    ),
                    "commit_message": OpenAIToolParameterProperty(description="Meaningful commit name"),
                },
                required=["branch_name", "commit_message"],
            ),
        ),
        handler=_merge_request_factory.create_commit_in_branch,
    ),
    OpenAITool(
        function=OpenAIFunction(
            description="Creates merge request from previously created commits. Once tested, merge request will be automatically merged to repository! IMPORTANT: `create_merge_request` requires `add_file_to_merge_request` and `create_commit_in_branch` to be run at least once!",
            name="create_merge_request",
            parameters=OpenAIToolParameter(
                properties={
                    "title": OpenAIToolParameterProperty(description="Title of the merge request"),
                    "description": OpenAIToolParameterProperty(
                        description="Description of the merge request. IMPORTANT: Description must be meaningful also containing short summary of the alert that's being fixed"
                    ),
                },
                required=["title", "description"],
            ),
        ),
        handler=_merge_request_factory.create_merge_request,
    ),
]
