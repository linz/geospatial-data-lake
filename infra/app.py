#!/usr/bin/env python3

"""
CDK application entry point file.
"""

import os

from aws_cdk import core
from datalake.api_stack import APIStack  # pylint: disable=import-error
from datalake.networking_stack import NetworkingStack  # pylint: disable=import-error
from datalake.processing_stack import ProcessingStack  # pylint: disable=import-error
from datalake.storage_stack import StorageStack  # pylint: disable=import-error

ENV = os.environ.get("DEPLOY_ENV", "dev")


app = core.App()

networking = NetworkingStack(
    app,
    "networking",
    stack_name=f"geospatial-data-lake-networking-{ENV}",
    env={"region": os.environ["CDK_DEFAULT_REGION"], "account": os.environ["CDK_DEFAULT_ACCOUNT"]},
)

storage = StorageStack(
    app,
    "storage",
    stack_name=f"geospatial-data-lake-storage-{ENV}",
    env={"region": os.environ["CDK_DEFAULT_REGION"], "account": os.environ["CDK_DEFAULT_ACCOUNT"]},
    deploy_env=ENV,
)

processing = ProcessingStack(
    app,
    "processing",
    stack_name=f"geospatial-data-lake-processing-{ENV}",
    env={"region": os.environ["CDK_DEFAULT_REGION"], "account": os.environ["CDK_DEFAULT_ACCOUNT"]},
    deploy_env=ENV,
    vpc=networking.datalake_vpc,
)

api = APIStack(
    app,
    "api",
    stack_name=f"geospatial-data-lake-api-{ENV}",
    env={"region": os.environ["CDK_DEFAULT_REGION"], "account": os.environ["CDK_DEFAULT_ACCOUNT"]},
    datasets_table=storage.datasets_table,
)

# tag all resources in stack
core.Tag.add(app, "CostCentre", "100005")
core.Tag.add(app, "ApplicationName", "geospatial-data-lake")
core.Tag.add(app, "Owner", "Bill M. Nelson")
core.Tag.add(app, "EnvironmentType", f"{ENV}")
core.Tag.add(app, "SupportType", "Dev")
core.Tag.add(app, "HoursOfOperation", "24x7")

app.synth()
