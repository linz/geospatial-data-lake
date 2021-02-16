"""
Data Lake processing stack.
"""
from typing import Any

from aws_cdk import aws_iam, aws_ssm, aws_stepfunctions, core

from .backend.endpoints.dataset_versions.create import DATASET_VERSION_CREATION_STEP_FUNCTION
from .backend.endpoints.utils import ResourceName
from .backend.processing.content_iterator.task import MAX_ITERATION_SIZE
from .constructs.batch_job_queue import BatchJobQueue
from .constructs.batch_submit_job_task import BatchSubmitJobTask
from .constructs.lambda_task import LambdaTask
from .constructs.table import Table


class ProcessingStack(core.Stack):
    """Data Lake processing stack definition."""

    def __init__(
        self,
        scope: core.Construct,
        stack_id: str,
        deploy_env: str,
        **kwargs: Any,
    ) -> None:
        # pylint: disable=too-many-locals
        super().__init__(scope, stack_id, **kwargs)

        application_layer = "data-processing"

        ############################################################################################
        # PROCESSING ASSETS TABLE
        processing_assets_table = Table(
            self,
            ResourceName.PROCESSING_ASSETS_TABLE_NAME.value,
            deploy_env=deploy_env,
            application_layer=application_layer,
        )

        ############################################################################################
        # BATCH JOB DEPENDENCIES
        batch_job_queue = BatchJobQueue(
            self,
            "batch_job_queue",
            deploy_env=deploy_env,
            processing_assets_table=processing_assets_table,
        ).job_queue

        s3_read_only_access_policy = aws_iam.ManagedPolicy.from_aws_managed_policy_name(
            "AmazonS3ReadOnlyAccess"
        )

        ############################################################################################
        # STATE MACHINE TASKS
        check_stac_metadata_job_task = BatchSubmitJobTask(
            self,
            "check_stac_metadata_task",
            deploy_env=deploy_env,
            directory="check_stac_metadata",
            s3_policy=s3_read_only_access_policy,
            job_queue=batch_job_queue,
            payload_object={
                "dataset_id.$": "$.dataset_id",
                "version_id.$": "$.version_id",
                "type.$": "$.type",
                "metadata_url.$": "$.metadata_url",
            },
            container_overrides_command=[
                "--dataset-id",
                "Ref::dataset_id",
                "--version-id",
                "Ref::version_id",
                "--metadata-url",
                "Ref::metadata_url",
            ],
        )
        processing_assets_table.grant_read_write_data(
            check_stac_metadata_job_task.job_role  # type: ignore[arg-type]
        )
        processing_assets_table.grant(
            check_stac_metadata_job_task.job_role,  # type: ignore[arg-type]
            "dynamodb:DescribeTable",
        )

        content_iterator_task = LambdaTask(
            self,
            "content_iterator_task",
            directory="content_iterator",
            result_path="$.content",
            application_layer=application_layer,
            extra_environment={"DEPLOY_ENV": deploy_env},
        )
        processing_assets_table.grant_read_write_data(content_iterator_task.lambda_function)
        processing_assets_table.grant(
            content_iterator_task.lambda_function, "dynamodb:DescribeTable"
        )

        check_files_checksums_task = BatchSubmitJobTask(
            self,
            "check_files_checksums_task",
            deploy_env=deploy_env,
            directory="check_files_checksums",
            s3_policy=s3_read_only_access_policy,
            job_queue=batch_job_queue,
            payload_object={
                "dataset_id.$": "$.dataset_id",
                "version_id.$": "$.version_id",
                "type.$": "$.type",
                "metadata_url.$": "$.metadata_url",
                "first_item.$": "$.content.first_item",
                "iteration_size.$": "$.content.iteration_size",
            },
            array_size=MAX_ITERATION_SIZE,
            container_overrides_command=[
                "--dataset-id",
                "Ref::dataset_id",
                "--version-id",
                "Ref::version_id",
                "--first-item",
                "Ref::first_item",
            ],
        )
        processing_assets_table.grant_read_data(
            check_files_checksums_task.job_role  # type: ignore[arg-type]
        )
        processing_assets_table.grant(
            check_files_checksums_task.job_role, "dynamodb:DescribeTable"  # type: ignore[arg-type]
        )

        validation_summary_lambda_invoke = LambdaTask(
            self,
            "validation_summary_task",
            directory="validation_summary",
            result_path="$.validation",
            application_layer=application_layer,
        ).lambda_invoke

        validation_failure_lambda_invoke = LambdaTask(
            self,
            "validation_failure_task",
            directory="validation_failure",
            result_path=aws_stepfunctions.JsonPath.DISCARD,
            application_layer=application_layer,
        ).lambda_invoke

        success_task = aws_stepfunctions.Succeed(self, "success")

        ############################################################################################
        # STATE MACHINE
        dataset_version_creation_definition = (
            check_stac_metadata_job_task.batch_submit_job.next(content_iterator_task.lambda_invoke)
            .next(check_files_checksums_task.batch_submit_job)
            .next(
                aws_stepfunctions.Choice(self, "content_iteration_finished")
                .when(
                    aws_stepfunctions.Condition.not_(
                        aws_stepfunctions.Condition.string_equals("$.content.next_item", "-1")
                    ),
                    content_iterator_task.lambda_invoke,
                )
                .otherwise(
                    validation_summary_lambda_invoke.next(
                        aws_stepfunctions.Choice(  # type: ignore[arg-type]
                            self, "validation_successful"
                        )
                        .when(
                            aws_stepfunctions.Condition.boolean_equals(
                                "$.validation.success", True
                            ),
                            success_task,  # type: ignore[arg-type]
                        )
                        .otherwise(validation_failure_lambda_invoke)
                    )
                )
            )
        )

        state_machine = aws_stepfunctions.StateMachine(
            self,
            f"{deploy_env}-dataset-version-creation",
            definition=dataset_version_creation_definition,  # type: ignore[arg-type]
        )

        aws_ssm.StringParameter(
            self,
            "StepFunctionStateMachineARN",
            description=f"Step Function State Machine ARN for {deploy_env}",
            parameter_name=DATASET_VERSION_CREATION_STEP_FUNCTION,
            string_value=state_machine.state_machine_arn,
        )
