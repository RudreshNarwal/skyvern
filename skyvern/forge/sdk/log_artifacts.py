import json
import structlog

import functools
from typing import Callable

from skyvern.forge import app
from skyvern.forge.sdk.core import skyvern_context
from skyvern.forge.skyvern_json_encoder import SkyvernJSONLogEncoder
from skyvern.forge.skyvern_log_encoder import SkyvernLogEncoder
from skyvern.forge.sdk.artifact.models import ArtifactType, LogEntityType

LOG = structlog.get_logger()

def with_skyvern_context(func: Callable):
    """
    Decorator to ensure the presence of a Skyvern context for a function.
    If no context is available, the function will not execute.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        context = skyvern_context.current()
        if not context:
            LOG.warning("No Skyvern context found, skipping function execution", func=func.__name__)
            return
        return await func(*args, **kwargs)

    return wrapper

def primary_key_from_log_entity_type(log_entity_type: LogEntityType) -> str:
    if log_entity_type == LogEntityType.STEP:
        return "step_id"
    elif log_entity_type == LogEntityType.TASK:
        return "task_id"
    elif log_entity_type == LogEntityType.WORKFLOW_RUN:
        return "workflow_run_id"
    elif log_entity_type == LogEntityType.WORKFLOW_RUN_BLOCK:
        return "workflow_run_block_id"
    else:
        raise ValueError(f"Invalid log entity type: {log_entity_type}")

@with_skyvern_context
async def save_step_logs(step_id: str) -> None:
    log = skyvern_context.current().log
    organization_id = skyvern_context.current().organization_id

    current_step_log = [entry for entry in log if entry.get("step_id", "") == step_id]

    await _save_log_artifacts(
        log=current_step_log,
        log_entity_type=LogEntityType.STEP,
        log_entity_id=step_id,
        organization_id=organization_id,
        step_id=step_id,
    )


@with_skyvern_context
async def save_task_logs(task_id: str) -> None:
    log = skyvern_context.current().log
    organization_id = skyvern_context.current().organization_id

    current_task_log = [entry for entry in log if entry.get("task_id", "") == task_id]

    await _save_log_artifacts(
        log=current_task_log,
        log_entity_type=LogEntityType.TASK,
        log_entity_id=task_id,
        organization_id=organization_id,
        task_id=task_id,
    )


@with_skyvern_context
async def save_workflow_run_logs(workflow_run_id: str) -> None:
    log = skyvern_context.current().log
    organization_id = skyvern_context.current().organization_id

    current_workflow_run_log = [entry for entry in log if entry.get("workflow_run_id", "") == workflow_run_id]

    await _save_log_artifacts(
        log=current_workflow_run_log,
        log_entity_type=LogEntityType.WORKFLOW_RUN,
        log_entity_id=workflow_run_id,
        organization_id=organization_id,
        workflow_run_id=workflow_run_id,
    )


@with_skyvern_context
async def save_workflow_run_block_logs(workflow_run_block_id: str) -> None:
    log = skyvern_context.current().log
    organization_id = skyvern_context.current().organization_id
    current_workflow_run_block_log = [entry for entry in log if entry.get("workflow_run_block_id", "") == workflow_run_block_id]

    await _save_log_artifacts(
        log=current_workflow_run_block_log,
        log_entity_type=LogEntityType.WORKFLOW_RUN_BLOCK,
        log_entity_id=workflow_run_block_id,
        organization_id=organization_id,
        workflow_run_block_id=workflow_run_block_id,
    )


async def _save_log_artifacts(
    log: list[dict],
    log_entity_type: LogEntityType,
    log_entity_id: str,
    organization_id: str,
    step_id: str | None = None,
    task_id: str | None = None,
    workflow_run_id: str | None = None,
    workflow_run_block_id: str | None = None,
) -> None:
    try:
        log_json = json.dumps(log, cls=SkyvernJSONLogEncoder, indent=2)

        log_artifact = await app.DATABASE.get_artifact_by_entity_id(
            artifact_type=ArtifactType.SKYVERN_LOG_RAW,
            step_id=step_id,
            task_id=task_id,
            workflow_run_id=workflow_run_id,
            workflow_run_block_id=workflow_run_block_id,
            organization_id=organization_id,
        )


        if log_artifact:
            await app.ARTIFACT_MANAGER.update_artifact_data(
                artifact_id=log_artifact.artifact_id,
                organization_id=organization_id,
                data=log_json.encode(),
                primary_key=primary_key_from_log_entity_type(log_entity_type),
            )
        else:
            await app.ARTIFACT_MANAGER.create_log_artifact(
                organization_id=organization_id,
                step_id=step_id,
                task_id=task_id,
                workflow_run_id=workflow_run_id,
                workflow_run_block_id=workflow_run_block_id,
                log_entity_type=log_entity_type,
                log_entity_id=log_entity_id,
                artifact_type=ArtifactType.SKYVERN_LOG_RAW,
                data=log_json.encode(),
            )

        formatted_log = SkyvernLogEncoder.encode(log)

        formatted_log_artifact = await app.DATABASE.get_artifact_by_entity_id(
            artifact_type=ArtifactType.SKYVERN_LOG,
            step_id=step_id,
            task_id=task_id,
            workflow_run_id=workflow_run_id,
            workflow_run_block_id=workflow_run_block_id,
            organization_id=organization_id,
        )

        if formatted_log_artifact:
            await app.ARTIFACT_MANAGER.update_artifact_data(
                artifact_id=formatted_log_artifact.artifact_id,
                organization_id=organization_id,
                data=formatted_log.encode(),
                primary_key=primary_key_from_log_entity_type(log_entity_type),
            )
        else:
            await app.ARTIFACT_MANAGER.create_log_artifact(
                organization_id=organization_id,
                step_id=step_id,
                task_id=task_id,
                workflow_run_id=workflow_run_id,
                workflow_run_block_id=workflow_run_block_id,
                log_entity_type=log_entity_type,
                log_entity_id=log_entity_id,
                artifact_type=ArtifactType.SKYVERN_LOG,
                data=formatted_log.encode(),
            )
    except Exception as e:
        LOG.error(
            "Failed to save log artifacts",
            log_entity_type=log_entity_type,
            log_entity_id=log_entity_id,
            organization_id=organization_id,
            step_id=step_id,
            task_id=task_id,
            workflow_run_id=workflow_run_id,
            workflow_run_block_id=workflow_run_block_id,
            exc_info=True,
        )

