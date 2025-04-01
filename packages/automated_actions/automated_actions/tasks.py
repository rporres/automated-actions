import logging

from celery import Celery
from celery.app.task import Task as CeleryTask

from automated_actions.config import settings
from automated_actions.utils.openshift_client import OpenshiftClient, RollingRestartResource
from automated_actions.api.models import Task

log = logging.getLogger(__name__)

app = Celery(
    "tasks",
    broker=settings.broker_url,
    broker_transport_options={
        "region": settings.broker_aws_region,
        "predefined_queues": {
            "celery": {
                "url": settings.sqs_url,
                "access_key_id": settings.broker_aws_access_key_id,
                "secret_access_key": settings.broker_aws_secret_access_key,
            }
        },
    },
    result_backend=settings.result_backend_url,
    broker_connection_retry_on_startup=True,
    worker_enable_remote_control=False,
    worker_log_format="[%(asctime)s: GJB] %(message)s",
    # support pydantic models
    task_serializer="pickle",
    result_serializer="pickle",
    event_serializer="json",
    accept_content=["application/json", "application/x-python-serialize"],
    result_accept_content=["application/json", "application/x-python-serialize"],
)


@app.task(bind=True)
def openshift_workload_restart(
    self: CeleryTask, cluster: str, namespace: str, kind: str, name: str, task: Task
) -> bool:
    log.info(self.request.id)

    oc = OpenshiftClient(server_url=SERVER_URL, token=TOKEN)

    if kind in RollingRestartResource:
        res = oc.rolling_restart(
            kind=RollingRestartResource(kind),
            name=name,
            namespace=namespace,
        )
    elif kind == "Pod":
        res = oc.delete_pod_from_replicated_resource(name=name, namespace=namespace)
    else:
        raise Exception(f"kind '{kind}' not supported")

    # do we need to keep res?
    if not res:
        pass

    return True
