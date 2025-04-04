# # ruff: noqa: ERA001
import logging
from typing import Any

from billiard.einfo import ExceptionInfo
from celery import Celery, Task

from automated_actions.actions.openshift_workload_restart import (
    OpenshiftWorkloadRestart,
)
from automated_actions.api.models import Action, ActionStatus
from automated_actions.config import settings
from automated_actions.utils.cluster_connection import get_cluster_connection_data
from automated_actions.utils.openshift_client import OpenshiftClient

# class Action:
#    def __init__(self, status: ActionStatus):
#        self._status = status
#        self.action_id = str(uuid.uuid4())
#
#    def set_status(self, status: ActionStatus) -> None:
#        self._status = status


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


class AutomatedActionTask(Task):
    autoretry_for = (Exception,)
    default_retry_delay = 15
    max_retries = 5

    def before_start(  # noqa: PLR6301
        self,
        task_id: str,  # noqa: ARG002
        args: tuple,  # noqa: ARG002
        kwargs: dict,
    ) -> None:
        log.warning(
            "action_id=%s set to %s", kwargs["task"].action_id, ActionStatus.RUNNING
        )
        kwargs["action"].set_status(ActionStatus.RUNNING)

    def on_success(  # noqa: PLR6301
        self,
        retval: Any,  # noqa: ARG002
        task_id: str,  # noqa: ARG002
        args: tuple,  # noqa: ARG002
        kwargs: dict,
    ) -> None:
        log.warning(
            "action_id=%s set to %s", kwargs["task"].action_id, ActionStatus.SUCCESS
        )
        kwargs["action"].set_status(ActionStatus.SUCCESS)
        kwargs["action"].set_result(
            f"kind {kwargs['kind']} {kwargs['name']} restarted successfully on"
            f"{kwargs['cluster']}/{kwargs['namespace']}"
        )

    def on_failure(  # noqa: PLR6301
        self,
        exc: Exception,  # noqa: ARG002
        task_id: str,  # noqa: ARG002
        args: tuple,  # noqa: ARG002
        kwargs: dict,
        einfo: ExceptionInfo,
    ) -> None:
        log.warning(
            "action_id=%s set to %s", kwargs["task"].action_id, ActionStatus.FAILURE
        )
        kwargs["action"].set_status(ActionStatus.FAILURE)
        kwargs["action"].set_result(
            f"kind {kwargs['kind']} {kwargs['name']} restart failed on"
            f"{kwargs['cluster']}/{kwargs['namespace']}: {einfo}"
        )

    def on_retry(  # noqa: PLR6301
        self,
        exc: Exception,  # noqa: ARG002
        task_id: str,  # noqa: ARG002
        args: tuple,  # noqa: ARG002
        kwargs: dict,
        einfo: ExceptionInfo,
    ) -> None:
        log.warning(
            "action_id=%s retrying due to %s", kwargs["action"].action_id, einfo
        )


@app.task(bind=True)
def openshift_workload_restart(
    cluster: str, namespace: str, kind: str, name: str, action: Action
) -> None:
    try:
        cluster_connection = get_cluster_connection_data(cluster)
        oc = OpenshiftClient(
            server_url=cluster_connection.url, token=cluster_connection.token
        )
        OpenshiftWorkloadRestart(oc, namespace, kind, name).run()
    except Exception:
        log.exception("action %s failed", action.action_id)

    log.info(
        "action_id=%s successful: %s %s restarted successfully on %s/%s",
        action.action_id,
        kind,
        name,
        cluster,
        namespace,
    )
