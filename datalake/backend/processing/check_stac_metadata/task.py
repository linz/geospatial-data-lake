#!/usr/bin/env python3
import logging
import sys
from argparse import ArgumentParser, Namespace
from json import dumps, load
from os import environ
from os.path import dirname, join
from typing import Callable, Dict, List, TextIO
from urllib.parse import urlparse

import boto3
from botocore.response import StreamingBody  # type: ignore[import]
from jsonschema import (  # type: ignore[import]
    Draft7Validator,
    FormatChecker,
    RefResolver,
    ValidationError,
)
from jsonschema._utils import URIDict  # type: ignore[import]
from pynamodb.attributes import UnicodeAttribute
from pynamodb.models import Model

ENV = environ["DEPLOY_ENV"]
PROCESSING_ASSETS_TABLE_NAME = f"{ENV}-processing-assets"

S3_URL_PREFIX = "s3://"

SCRIPT_DIR = dirname(__file__)
COLLECTION_SCHEMA_PATH = join(SCRIPT_DIR, "stac-spec/collection-spec/json-schema/collection.json")
CATALOG_SCHEMA_PATH = join(SCRIPT_DIR, "stac-spec/catalog-spec/json-schema/catalog.json")


class ProcessingAssetsModel(Model):
    class Meta:  # pylint:disable=too-few-public-methods
        table_name = PROCESSING_ASSETS_TABLE_NAME
        region = "ap-southeast-2"  # TODO: don't hardcode region

    pk = UnicodeAttribute(hash_key=True)
    sk = UnicodeAttribute(range_key=True)
    url = UnicodeAttribute()
    multihash = UnicodeAttribute()


class STACSchemaValidator:  # pylint:disable=too-few-public-methods
    def __init__(self, url_reader: Callable[[str], TextIO]):
        self.url_reader = url_reader
        self.traversed_urls: List[str] = []

        with open(COLLECTION_SCHEMA_PATH) as collection_schema_file:
            collection_schema = load(collection_schema_file)

        with open(CATALOG_SCHEMA_PATH) as catalog_schema_file:
            catalog_schema = load(catalog_schema_file)

        # Normalize URLs the same way as jsonschema does
        uri_dictionary = URIDict()
        schema_store = {
            uri_dictionary.normalize(collection_schema["$id"]): collection_schema,
            uri_dictionary.normalize(catalog_schema["$id"]): catalog_schema,
        }

        resolver = RefResolver.from_schema(collection_schema, store=schema_store)
        self.validator = Draft7Validator(
            collection_schema, resolver=resolver, format_checker=FormatChecker()
        )

    def validate(self, url: str) -> List[Dict[str, str]]:
        assert url[:5] == S3_URL_PREFIX, f"URL doesn't start with “{S3_URL_PREFIX}”: “{url}”"

        self.traversed_urls.append(url)

        url_stream = self.url_reader(url)
        url_json = load(url_stream)

        self.validator.validate(url_json)

        assets = []
        for asset in url_json.get("assets", {}).values():
            assets.append({"url": asset["href"], "multihash": asset["checksum:multihash"]})

        for link_object in url_json["links"]:
            next_url = link_object["href"]
            if next_url not in self.traversed_urls:
                url_prefix = url.rsplit("/", maxsplit=1)[0]
                next_url_prefix = next_url.rsplit("/", maxsplit=1)[0]
                assert (
                    url_prefix == next_url_prefix
                ), f"“{url}” links to metadata file in different directory: “{next_url}”"

                assets.extend(self.validate(next_url))

        return assets


def parse_arguments() -> Namespace:
    argument_parser = ArgumentParser()
    argument_parser.add_argument("--metadata-url", required=True)
    argument_parser.add_argument("--dataset-id", required=True)
    argument_parser.add_argument("--version-id", required=True)
    arguments = argument_parser.parse_args()
    return arguments


def s3_url_reader() -> Callable[[str], StreamingBody]:
    client = boto3.client("s3")

    def read(href: str) -> StreamingBody:
        parse_result = urlparse(href, allow_fragments=False)
        bucket_name = parse_result.netloc
        key = parse_result.path[1:]
        response = client.get_object(Bucket=bucket_name, Key=key)
        return response["Body"]

    return read


def set_up_logging() -> logging.Logger:
    logger = logging.getLogger(__name__)

    log_handler = logging.StreamHandler()
    log_level = environ.get("LOGLEVEL", logging.NOTSET)

    logger.addHandler(log_handler)
    logger.setLevel(log_level)

    return logger


def main() -> int:
    logger = set_up_logging()

    arguments = parse_arguments()
    logger.debug(dumps({"arguments": vars(arguments)}))

    url_reader = s3_url_reader()

    try:
        assets = STACSchemaValidator(url_reader).validate(arguments.metadata_url)
    except (AssertionError, ValidationError) as error:
        logger.error(dumps({"success": False, "message": str(error)}))
        return 1

    asset_pk = f"DATASET#{arguments.dataset_id}#VERSION#{arguments.version_id}"
    for index, asset in enumerate(assets):
        ProcessingAssetsModel(
            pk=asset_pk,
            sk=f"DATA_ITEM_INDEX#{index}",
            url=asset["url"],
            multihash=asset["multihash"],
        ).save()

    logger.info(dumps({"success": True, "message": ""}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
