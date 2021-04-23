from functools import lru_cache
from json import JSONDecodeError, dumps, load
from os.path import dirname
from typing import Any, Callable, List, Tuple
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError  # type: ignore[import]
from botocore.response import StreamingBody  # type: ignore[import]
from pystac import STAC_IO  # type: ignore[import]
from pystac.validation import (  # type: ignore[import]
    STACValidationError,
    set_validator,
    validate_all,
)

from ..check import Check
from ..log import set_up_logging
from ..processing_assets_model import ProcessingAssetType, processing_assets_model_with_meta
from ..types import JsonObject
from ..validation_results_model import ValidationResult, ValidationResultFactory
from .stac_validators import DataLakeSTACValidator

LOGGER = set_up_logging(__name__)

STAC_COLLECTION_TYPE = "Collection"
STAC_ITEM_TYPE = "Feature"
STAC_CATALOG_TYPE = "Catalog"


S3_URL_PREFIX = "s3://"
S3_CLIENT = boto3.client("s3")


def s3_read_method(url: str) -> StreamingBody:
    # pylint: disable=no-else-return

    parse_result = urlparse(url, allow_fragments=False)
    if parse_result.scheme == "s3":
        bucket_name = parse_result.netloc
        key = parse_result.path[1:]
        response = S3_CLIENT.get_object(Bucket=bucket_name, Key=key)
        return response["Body"].read().decode("utf-8")
    else:
        return STAC_IO.default_read_text_method(url)


@lru_cache
def maybe_convert_relative_url_to_absolute(url_or_path: str, parent_url: str) -> str:
    if url_or_path[:5] == S3_URL_PREFIX:
        return url_or_path

    return f"{dirname(parent_url)}/{url_or_path}"


class STACDatasetValidator:
    def __init__(
        self,
        url_reader: Callable[[str], StreamingBody],
        validation_result_factory: ValidationResultFactory,
    ):
        self.url_reader = url_reader
        self.validation_result_factory = validation_result_factory

        self.processing_assets_model = processing_assets_model_with_meta()
        self.datalake_validator = DataLakeSTACValidator(validation_result_factory)

        STAC_IO.read_text_method = s3_read_method
        set_validator(self.datalake_validator)

    def run(self, metadata_url: str, hash_key: str) -> None:
        if metadata_url[:5] != S3_URL_PREFIX:
            error_message = f"URL doesn't start with “{S3_URL_PREFIX}”: “{metadata_url}”"
            self.validation_result_factory.save(
                metadata_url,
                Check.NON_S3_URL,
                ValidationResult.FAILED,
                details={"message": error_message},
            )
            LOGGER.error(dumps({"success": False, "message": error_message}))
            return

        try:
            self.validate(metadata_url)
        except (STACValidationError, ClientError, JSONDecodeError) as error:
            LOGGER.error(dumps({"success": False, "message": str(error)}))
            return

        for index, metadata_file in enumerate(self.datalake_validator.dataset_metadata):
            self.processing_assets_model(
                hash_key=hash_key,
                range_key=f"{ProcessingAssetType.METADATA.value}#{index}",
                url=metadata_file["url"],
            ).save()

        for index, asset in enumerate(self.datalake_validator.dataset_assets):
            self.processing_assets_model(
                hash_key=hash_key,
                range_key=f"{ProcessingAssetType.DATA.value}#{index}",
                url=asset["url"],
                multihash=asset["multihash"],
            ).save()

    def validate(self, url: str) -> None:  # pylint: disable=too-complex
        object_json = self.get_object(url)

        try:
            validate_all(object_json, url)
        except STACValidationError as error:
            self.validation_result_factory.save(
                url,
                Check.JSON_SCHEMA,
                ValidationResult.FAILED,
                details={"message": str(error)},
            )
            raise

    def get_object(self, url: str) -> JsonObject:
        try:
            url_stream = self.url_reader(url)
        except ClientError as error:
            self.validation_result_factory.save(
                url,
                Check.STAGING_ACCESS,
                ValidationResult.FAILED,
                details={"message": str(error)},
            )
            raise
        try:
            json_object: JsonObject = load(
                url_stream, object_pairs_hook=self.duplicate_object_names_report_builder(url)
            )
        except JSONDecodeError as error:
            self.validation_result_factory.save(
                url, Check.JSON_PARSE, ValidationResult.FAILED, details={"message": str(error)}
            )
            raise
        return json_object

    def duplicate_object_names_report_builder(
        self, url: str
    ) -> Callable[[List[Tuple[str, Any]]], JsonObject]:
        def report_duplicate_object_names(object_pairs: List[Tuple[str, Any]]) -> JsonObject:
            result = {}
            for key, value in object_pairs:
                if key in result:
                    self.validation_result_factory.save(
                        url,
                        Check.DUPLICATE_OBJECT_KEY,
                        ValidationResult.FAILED,
                        details={"message": f"Found duplicate object name “{key}” in “{url}”"},
                    )
                else:
                    result[key] = value
            return result

        return report_duplicate_object_names


@lru_cache
def get_url_before_filename(url: str) -> str:
    return url.rsplit("/", maxsplit=1)[0]
