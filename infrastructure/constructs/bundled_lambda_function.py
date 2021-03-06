from typing import Mapping, Optional

from aws_cdk import aws_lambda, aws_lambda_python
from aws_cdk.core import Construct, Duration

from ..common import LOG_LEVEL
from ..runtime import PYTHON_RUNTIME
from .backend import BACKEND_DIRECTORY
from .bundled_code import bundled_code


class BundledLambdaFunction(aws_lambda.Function):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        directory: str,
        extra_environment: Optional[Mapping[str, str]],
        botocore_lambda_layer: aws_lambda_python.PythonLayerVersion,
    ):
        environment = {"LOGLEVEL": LOG_LEVEL}
        if extra_environment is not None:
            environment.update(extra_environment)

        super().__init__(
            scope,
            construct_id,
            code=bundled_code(directory),
            handler=f"{BACKEND_DIRECTORY}.{directory}.task.lambda_handler",
            runtime=PYTHON_RUNTIME,
            environment=environment,
            layers=[botocore_lambda_layer],  # type: ignore[list-item]
            timeout=Duration.seconds(60),
        )
