from enum import Enum, auto
from functools import lru_cache
from json import dumps
from typing import Sequence

import boto3

from .environment import ENV
from .error_response_keys import ERROR_KEY
from .log import set_up_logging

LOGGER = set_up_logging(__name__)
SSM_CLIENT = boto3.client("ssm")


class ParameterName(Enum):
    # Use @staticmethod instead of all the ignores on the next line once we move to Python 3.9
    # <https://github.com/python/mypy/issues/7591>.
    def _generate_next_value_(  # type: ignore[misc,override] # pylint:disable=no-self-argument,no-member
        name: str, _start: int, _count: int, _last_values: Sequence[str]
    ) -> str:
        return f"/{ENV}/{name.lower()}"

    PROCESSING_ASSETS_TABLE_NAME = auto()
    PROCESSING_DATASET_VERSION_CREATION_STEP_FUNCTION_ARN = auto()
    PROCESSING_IMPORT_ASSET_FILE_FUNCTION_TASK_ARN = auto()
    PROCESSING_IMPORT_DATASET_ROLE_ARN = auto()
    PROCESSING_IMPORT_METADATA_FILE_FUNCTION_TASK_ARN = auto()
    STORAGE_DATASETS_TABLE_NAME = auto()
    STORAGE_VALIDATION_RESULTS_TABLE_NAME = auto()


@lru_cache
def get_param(parameter: ParameterName) -> str:
    try:
        parameter_response = SSM_CLIENT.get_parameter(Name=parameter.value)
    except SSM_CLIENT.exceptions.ParameterNotFound:
        LOGGER.error(dumps({ERROR_KEY: f"Parameter not found: “{parameter.value}”"}))
        raise

    try:
        return parameter_response["Parameter"]["Value"]
    except KeyError as error:
        LOGGER.error(dumps({ERROR_KEY: error}, default=str))
        raise
