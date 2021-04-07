from argparse import ArgumentParser, Namespace
from functools import lru_cache
from json import dumps, load
from logging import Logger
from os.path import dirname
from typing import Any, Callable, Dict, List, Type, Union

from botocore.exceptions import ClientError  # type: ignore[import]
from botocore.response import StreamingBody  # type: ignore[import]
from jsonschema import ValidationError  # type: ignore[import]

from ..check import Check
from ..log import set_up_logging
from ..processing_assets_model import ProcessingAssetType, processing_assets_model_with_meta
from ..validation_results_model import ValidationResult, ValidationResultFactory
from .stac_validators import (
    STACCatalogSchemaValidator,
    STACCollectionSchemaValidator,
    STACItemSchemaValidator,
)

LOGGER = set_up_logging(__name__)

STAC_COLLECTION_TYPE = "Collection"
STAC_ITEM_TYPE = "Feature"
STAC_CATALOG_TYPE = "Catalog"

STAC_TYPE_VALIDATION_MAP: Dict[
    str,
    Union[
        Type[STACCatalogSchemaValidator],
        Type[STACCollectionSchemaValidator],
        Type[STACItemSchemaValidator],
    ],
] = {
    STAC_COLLECTION_TYPE: STACCollectionSchemaValidator,
    STAC_CATALOG_TYPE: STACCatalogSchemaValidator,
    STAC_ITEM_TYPE: STACItemSchemaValidator,
}

S3_URL_PREFIX = "s3://"


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

        self.traversed_urls: List[str] = []
        self.dataset_assets: List[Dict[str, str]] = []
        self.dataset_metadata: List[Dict[str, str]] = []

        self.processing_assets_model = processing_assets_model_with_meta()

    def run(self, metadata_url: str) -> None:
        if metadata_url[:5] != S3_URL_PREFIX:
            error_message = f"URL doesn't start with “{S3_URL_PREFIX}”: “{metadata_url}”"
            self.validation_result_factory.save(
                metadata_url,
                Check.NON_S3_URL,
                ValidationResult.FAILED,
                details={"message": error_message},
            )
            raise AssertionError(error_message)
        self.validate(metadata_url)

    def validate(self, url: str) -> None:  # pylint: disable=too-complex
        self.traversed_urls.append(url)
        object_json = self.get_object(url)

        stac_type = object_json["type"]
        validator = STAC_TYPE_VALIDATION_MAP[stac_type]()

        try:
            validator.validate(object_json)
        except ValidationError as error:
            self.validation_result_factory.save(
                url,
                Check.JSON_SCHEMA,
                ValidationResult.FAILED,
                details={"message": str(error)},
            )
            raise
        self.validation_result_factory.save(url, Check.JSON_SCHEMA, ValidationResult.PASSED)
        self.dataset_metadata.append({"url": url})

        for asset in object_json.get("assets", {}).values():
            asset_url = maybe_convert_relative_url_to_absolute(asset["href"], url)

            asset_dict = {"url": asset_url, "multihash": asset["checksum:multihash"]}
            LOGGER.debug(dumps({"asset": asset_dict}))
            self.dataset_assets.append(asset_dict)

        for link_object in object_json["links"]:
            next_url = maybe_convert_relative_url_to_absolute(link_object["href"], url)

            if next_url not in self.traversed_urls:
                self.validate(next_url)

    def get_object(self, url: str) -> Any:
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
        return load(url_stream)

    def save(self, key: str) -> None:
        for index, metadata_file in enumerate(self.dataset_metadata):
            self.processing_assets_model(
                hash_key=key,
                range_key=f"{ProcessingAssetType.METADATA.value}#{index}",
                url=metadata_file["url"],
            ).save()

        for index, asset in enumerate(self.dataset_assets):
            self.processing_assets_model(
                hash_key=key,
                range_key=f"{ProcessingAssetType.DATA.value}#{index}",
                url=asset["url"],
                multihash=asset["multihash"],
            ).save()


@lru_cache
def get_url_before_filename(url: str) -> str:
    return url.rsplit("/", maxsplit=1)[0]


def parse_arguments(logger: Logger) -> Namespace:
    argument_parser = ArgumentParser()
    argument_parser.add_argument("--metadata-url", required=True)
    argument_parser.add_argument("--dataset-id", required=True)
    argument_parser.add_argument("--version-id", required=True)
    arguments = argument_parser.parse_args()
    logger.debug(dumps({"arguments": vars(arguments)}))
    return arguments
