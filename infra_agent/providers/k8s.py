import base64
import gzip
import json
import logging
from io import StringIO
from re import match
from typing import Any

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient
from ruamel.yaml import YAML

from infra_agent.models.generic import PromptToolError, SuccessPromptSummary
from infra_agent.models.k8s import (
    HelmReleaseMetadata,
    KubernetesAnyList,
    KubernetesCapacity,
    KubernetesCapacityNodeReport,
    KubernetesPodLogs,
    Node,
    Pod,
)
from infra_agent.providers.gl import get_file_contents, list_files_in_branch

logger = logging.getLogger(__name__)


# Label prefixes to filter out from node labels
EXCLUDED_LABEL_PREFIXES = [
    "feature.node.kubernetes.io/",
    "node.kubernetes.io/",
    "beta.kubernetes.io/",
    "kubernetes.io/",
    "k8s.io/",
    "node-role.kubernetes.io/",
]


async def _load_config():
    try:
        config.load_incluster_config()
    except Exception:
        await config.load_kube_config()


async def _filter_node_labels(labels: dict[str, str] | None) -> dict[str, str]:
    await _load_config()
    """Filter out system labels based on predefined prefixes."""
    if not labels:
        return {}

    result = {}
    for k, v in labels.items():
        if any(k.startswith(prefix) for prefix in EXCLUDED_LABEL_PREFIXES):
            continue
        result[k] = v
    return result


async def _validate_namespace(namespace: str) -> bool:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        ret = await v1.list_namespace()
        return namespace in [item.metadata.name for item in ret.items]


async def __redact_enc_values(obj: Any) -> Any:
    """Recursively walk a structure (dicts, lists, objects) and replace any
    string value starting with the prefix "ENC" with the literal "redacted".

    The function mutates the structure in-place and also returns it for
    convenience.
    """
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            v = obj[k]
            if isinstance(v, str) and v.startswith("ENC"):
                obj[k] = "redacted"
            else:
                await __redact_enc_values(v)
        return obj

    if isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str) and v.startswith("ENC"):
                obj[i] = "redacted"
            else:
                await __redact_enc_values(v)
        return obj

    # Plain string at top-level
    if isinstance(obj, str):
        return "redacted" if obj.startswith("ENC") else obj

    # Generic object with attributes (e.g., Kubernetes API objects)
    if hasattr(obj, "__dict__"):
        for attr, val in vars(obj).items():
            if isinstance(val, str) and val.startswith("ENC"):
                setattr(obj, attr, "redacted")
            else:
                await __redact_enc_values(val)
        return obj

    # Nothing to do for other types
    return obj


async def list_namespaces() -> KubernetesAnyList:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        ret = None
        try:
            ret = await v1.list_namespace()
        except Exception:
            raise PromptToolError(
                message="Failed to list namespaces",
                tool_name="list_namespaces_error",
                inputs={},
            )
        return KubernetesAnyList(items=[item.metadata.name for item in ret.items])


async def list_nodes() -> KubernetesAnyList:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        ret = None
        try:
            ret = await v1.list_node()
        except Exception:
            raise PromptToolError(
                message="Failed to list nodes",
                tool_name="list_nodes",
                inputs={},
            )

        # Convert to dict and modify labels before validation
        data = ret.to_dict()

        return KubernetesAnyList(items=[n["metadata"]["name"] for n in data["items"]])


async def get_node_details(node_name: str, include_labels: bool = False, include_annotations=False) -> Node:
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        ret = None
        try:
            ret = await v1.read_node(node_name)
            data = ret.to_dict()
            node = Node.model_validate(data)
            node.metadata.labels = (
                await _filter_node_labels(node.metadata.labels if node.metadata.labels else {})
                if include_labels
                else {}
            )
            node.metadata.annotations = node.metadata.annotations if include_annotations else {}
            return node
        except Exception:
            raise PromptToolError(
                message="Failed to list nodes",
                tool_name="list_nodes",
                inputs={},
            )


async def list_containers_in_pod(namespace: str, pod_name: str) -> KubernetesAnyList:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        ret = None
        try:
            if not await _validate_namespace(namespace):
                raise PromptToolError(
                    message="No such namespace",
                    tool_name="list_containers_in_pod",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                    },
                )
            ret = await v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            pod = Pod.model_validate(ret.to_dict())
            return KubernetesAnyList(items=[c.name for c in pod.spec.containers])
        except Exception:
            raise PromptToolError(
                message="Failed to list containers in pod",
                tool_name="list_pod_containers",
                inputs={
                    "namespace": namespace,
                    "pod_name": pod_name,
                },
            )


async def get_pod_container_logs(
    namespace: str, pod_name: str, container_name: str, tail_lines: int = 10
) -> KubernetesPodLogs:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        ret = None
        try:
            if not await _validate_namespace(namespace):
                raise PromptToolError(
                    message="No such namespace",
                    tool_name="get_pod_container_logs",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                        "container_name": container_name,
                    },
                )

            pods_in_namespaces = await list_pods_in_namespace(namespace)
            if pod_name not in pods_in_namespaces.items:
                raise PromptToolError(
                    message="No such pod in namespace",
                    tool_name="get_pod_container_logs",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                        "container_name": container_name,
                    },
                )

            ret = await v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container_name,
                tail_lines=tail_lines,
            )
        except Exception as e:
            logger.error(f"Error: {e}")
            raise PromptToolError(
                message=str(e),
                tool_name="get_pod_container_logs",
                inputs={
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "container_name": container_name,
                },
            )
        return KubernetesPodLogs(
            container_name=container_name,
            pod_name=pod_name,
            namespace=namespace,
            logs=ret.split("\n"),
        )


async def list_pods_in_namespace(namespace: str) -> KubernetesAnyList:
    await _load_config()
    if not await _validate_namespace(namespace):
        raise PromptToolError(
            message="No such namespace", tool_name="list_pods_in_namespace", inputs={"namespace": namespace}
        )

    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        ret = None
        try:
            if not await _validate_namespace(namespace):
                raise PromptToolError(
                    message="No such namespace", tool_name="list_pods_in_namespace", inputs={"namespace": namespace}
                )
            ret = await v1.list_namespaced_pod(namespace=namespace)
        except Exception:
            raise PromptToolError(
                message="Failed to list pods", tool_name="list_pods_in_namespace", inputs={"namespace": namespace}
            )
        # data = ret.to_dict()

        return KubernetesAnyList(items=[pod.metadata.name for pod in ret.items])


async def delete_pod(namespace: str, pod_name: str) -> SuccessPromptSummary:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        try:
            if not await _validate_namespace(namespace):
                raise PromptToolError(
                    message="No such namespace",
                    tool_name="delete_pod",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                    },
                )
            await v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        except Exception:
            raise PromptToolError(
                message="Failed to delete pod",
                tool_name="delete_pod",
                inputs={
                    "namespace": namespace,
                    "pod_name": pod_name,
                },
            )
        return SuccessPromptSummary()


async def get_pod_details(namespace: str, pod_name: str) -> Pod:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        pod = None
        try:
            if not await _validate_namespace(namespace):
                raise PromptToolError(
                    message="No such namespace",
                    tool_name="get_pod_details",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                    },
                )
            pod = await v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            return Pod.model_validate(pod.to_dict())
        except Exception:
            raise PromptToolError(
                message="No such pod",
                tool_name="get_pod_details",
                inputs={
                    "namespace": namespace,
                    "pod_name": pod_name,
                },
            )


async def list_pods_in_node(node_name: str) -> KubernetesAnyList:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        pods = None
        try:
            pods = await v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
        except Exception:
            raise PromptToolError(
                message="Failed to list node pods", tool_name="list_pods_in_node", inputs={"node_name": node_name}
            )
        return KubernetesAnyList(items=[pod.metadata.name for pod in pods.items])


async def get_node_resources(node_name: str) -> KubernetesCapacityNodeReport:
    await _load_config()
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        node = None
        try:
            node = await v1.read_node(name=node_name)
            # metrics_api = client.CustomObjectsApi(api)
            # node_metrics = await metrics_api.get_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes", node_name)

            capacity = node.status.capacity
            allocatable = node.status.allocatable
            return KubernetesCapacityNodeReport(
                name=node_name,
                capacity=KubernetesCapacity(
                    cpu=int(capacity.get("cpu")) if capacity.get("cpu", None) else None,
                    memory=capacity.get("memory", "unavailable"),
                    pods=int(capacity.get("pods")) if capacity.get("pods", None) else None,
                    ephemeral_storage=capacity.get("ephemeral-storage", "unavailable"),
                ),
                allocatable=KubernetesCapacity(
                    cpu=int(allocatable.get("cpu")) if allocatable.get("cpu", None) else None,
                    memory=capacity.get("memory", "unavailable"),
                    pods=int(allocatable.get("pods")) if allocatable.get("pods", None) else None,
                    ephemeral_storage=capacity.get("ephemeral-storage", "unavailable"),
                ),
            )
        except Exception as e:
            raise PromptToolError(
                message=f"Failed to get node resources: {e}",
                tool_name="get_node_resources",
                inputs={"node_name": node_name},
            )


async def get_helm_release_definition(namespace: str, pod_name: str) -> HelmReleaseMetadata:
    await _load_config()
    """
    Use only Kubernetes API to load the latest Helm release metadata for a given namespace and pod.
    Returns decoded metadata dict or error. Now also returns values.yaml if possible.
    """
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        try:
            if not await _validate_namespace(namespace):
                raise PromptToolError(
                    message="No such namespace",
                    tool_name="get_latest_helm_release_metadata",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                    },
                )
            secrets = await v1.list_namespaced_secret(namespace=namespace)
            helm_secrets = [s for s in secrets.items if s.metadata.name.startswith("sh.helm.release.v1.")]
            if not helm_secrets:
                raise PromptToolError(
                    message="Can't find Helm release for given container",
                    tool_name="get_latest_helm_release_metadata",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                    },
                )
            # Find the latest secret by creationTimestamp
            latest_secret = max(helm_secrets, key=lambda s: s.metadata.creation_timestamp or "")
            # The release data is in the 'data' field, key 'release'
            release_double_b64 = latest_secret.data.get("release") if latest_secret.data else None
            if not release_double_b64:
                raise PromptToolError(
                    message="No release data found in latest Helm secret",
                    tool_name="get_latest_helm_release_metadata",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                    },
                )
            release_b64 = base64.b64decode(release_double_b64)
            release_bytes = base64.b64decode(release_b64)
            # Helm stores a gzipped protobuf
            try:
                decompressed = gzip.decompress(release_bytes)
            except Exception:
                raise PromptToolError(
                    message="Couldn't parse Helm release metadata",
                    tool_name="get_latest_helm_release_metadata",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                    },
                )

            release_str = decompressed.decode("utf-8", errors="ignore")
            if "chart" in release_str:
                start = release_str.find("{")
                end = release_str.rfind("}") + 1
                metadata_json = release_str[start:end]
                try:
                    metadata = json.loads(metadata_json)
                    buf = StringIO()
                    default_values_yaml = YAML().dump(metadata["chart"]["values"], buf)

                    release_definition_file_paths = [
                        f"helmfiles/[a-z0-9_-]+/values/{metadata['name']}/[a-z0-9_-]+.yaml",
                        f"helmfiles/[a-z0-9_-]+/values/{metadata['name']}/[a-z0-9_-]+.secrets.yaml",
                    ]
                    values_yaml = {}
                    data = await list_files_in_branch("main")
                    for file_path in [
                        f.file_path for f in data if any([match(m, f.file_path) for m in release_definition_file_paths])
                    ]:
                        _f = await get_file_contents("main", file_path)
                        _f_content = _f.content
                        _f_yaml = YAML().load(_f_content)
                        if file_path.endswith(".secrets.yaml"):
                            del _f_yaml["sops"]
                            _f_yaml = await __redact_enc_values(_f_yaml)
                            _f_content = "# NOTE FOR AI:\n"
                            _f_content += "#   file was redacted from any secrets\n"
                            _f_content += "#   always treat `redacted` string as valid\n"
                            _f_content += "#   never edit this file\n\n"
                            buf = StringIO()
                            YAML().dump(_f_yaml, buf)
                            _f_content += buf.getvalue()
                        values_yaml[file_path] = _f_content

                    return HelmReleaseMetadata(
                        name=metadata["name"],
                        namespace=namespace,
                        chart_name=metadata["chart"]["metadata"]["name"],
                        default_values=default_values_yaml,
                        values=values_yaml,
                    )
                except Exception:
                    raise PromptToolError(
                        message="Couldn't parse Helm release metadata",
                        tool_name="get_latest_helm_release_metadata",
                        inputs={
                            "namespace": namespace,
                            "pod_name": pod_name,
                        },
                    )
            else:
                raise PromptToolError(
                    message="Couldn't parse Helm release metadata",
                    tool_name="get_latest_helm_release_metadata",
                    inputs={
                        "namespace": namespace,
                        "pod_name": pod_name,
                    },
                )
        except Exception:
            raise PromptToolError(
                message="Failed to decode pod's helm release metadata",
                tool_name="get_latest_helm_release_metadata",
                inputs={
                    "namespace": namespace,
                    "pod_name": pod_name,
                },
            )
