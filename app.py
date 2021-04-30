#!/usr/bin/env python3

"""
CDK application entry point file.
"""
from os import environ

from aws_cdk.core import App, Environment, Stack, Tag

from backend.environment import ENV
from infrastructure.api_stack import APIStack, APIStackProps
from infrastructure.constructs.batch_job_queue import APPLICATION_NAME, APPLICATION_NAME_TAG_NAME
from infrastructure.lambda_layers_stack import LambdaLayersStack
from infrastructure.lds import LDSStack, LDSStackProps
from infrastructure.processing_stack import ProcessingStack, ProcessingStackProps
from infrastructure.staging_stack import StagingStack
from infrastructure.storage_stack import StorageStack


def main() -> None:
    app = App()

    environment = Environment(
        account=environ["CDK_DEFAULT_ACCOUNT"], region=environ["CDK_DEFAULT_REGION"]
    )

    datalake = Stack(app, "datalake", env=environment, stack_name=f"{ENV}-geospatial-data-lake")

    storage = StorageStack(
        datalake,
        "storage",
        deploy_env=ENV,
    )

    StagingStack(datalake, "staging", deploy_env=ENV)

    lambda_layers = LambdaLayersStack(datalake, "lambda-layers", deploy_env=ENV)

    # can't get pylint working with Python dataclass
    processing_props = ProcessingStackProps(  # pylint:disable=unexpected-keyword-arg
        botocore_lambda_layer=lambda_layers.botocore,
        datasets_table=storage.datasets_table,
        storage_bucket=storage.storage_bucket,
        storage_bucket_parameter=storage.storage_bucket_parameter,
        validation_results_table=storage.validation_results_table,
    )
    processing = ProcessingStack(
        storage,
        "processing",
        deploy_env=ENV,
        props=processing_props,
    )

    # can't get pylint working with Python dataclass
    api_props = APIStackProps(  # pylint:disable=unexpected-keyword-arg
        botocore_lambda_layer=lambda_layers.botocore,
        datasets_table=storage.datasets_table,
        state_machine=processing.state_machine,
        state_machine_parameter=processing.state_machine_parameter,
        storage_bucket=storage.storage_bucket,
        storage_bucket_parameter=storage.storage_bucket_parameter,
        validation_results_table=storage.validation_results_table,
    )
    APIStack(
        processing,
        "api",
        deploy_env=ENV,
        props=api_props,
    )

    # can't get pylint working with Python dataclass
    lds_props = LDSStackProps(  # pylint:disable=unexpected-keyword-arg
        storage_bucket=storage.storage_bucket,
    )
    if app.node.try_get_context("enableLDSAccess"):
        LDSStack(
            storage,
            "lds",
            deploy_env=ENV,
            props=lds_props,
        )

    # tag all resources in stack
    Tag.add(app, "CostCentre", "100005")
    Tag.add(app, APPLICATION_NAME_TAG_NAME, APPLICATION_NAME)
    Tag.add(app, "Owner", "Bill M. Nelson")
    Tag.add(app, "EnvironmentType", ENV)
    Tag.add(app, "SupportType", "Dev")
    Tag.add(app, "HoursOfOperation", "24x7")

    app.synth()


if __name__ == "__main__":
    main()
