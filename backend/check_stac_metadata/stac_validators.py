import json
import typing
from json import load
from os.path import dirname, join
from typing import Dict, List

import jsonschema  # type: ignore[import]
from jsonschema._utils import URIDict  # type: ignore[import]
from pystac import STAC_IO, Collection, Item, STACObjectType  # type: ignore[import]
from pystac.validation import STACValidationError, STACValidator  # type: ignore[import]
from pystac.validation.schema_uri_map import DefaultSchemaUriMap  # type: ignore[import]

from ..types import JsonObject
from ..validation_results_model import ValidationResultFactory


class DataLakeSTACValidator(STACValidator):
    # pylint: disable=invalid-name
    # pylint: disable=too-many-arguments
    # pylint: disable=too-complex
    # pylint: disable=no-self-use

    """Validate STAC based on JSON Schemas.

    This validator uses JSON schemas, read from URIs provided by a
    :class:`~pystac.validation.SchemaUriMap`, to validate STAC core
    objects and extensions.

    Args:
        schema_uri_map (SchemaUriMap): The SchemaUriMap that defines where
            the validator will retrieve the JSON schemas for validation.
            Defaults to an instance of
            :class:`~pystac.validation.schema_uri_map.DefaultSchemaUriMap`

    Note:
    This class requires the ``jsonschema`` library to be installed.
    """

    @typing.no_type_check
    def __init__(self, validation_result_factory: ValidationResultFactory, schema_uri_map=None):
        if jsonschema is None:
            raise Exception("Cannot instantiate, requires jsonschema package")

        if schema_uri_map is not None:
            self.schema_uri_map = schema_uri_map
        else:
            self.schema_uri_map = DefaultSchemaUriMap()
        self.script_dir: str = dirname(__file__)
        self.schema_cache = {}
        self.dataset_assets: List[Dict[str, str]] = []
        self.dataset_metadata: List[Dict[str, str]] = []
        self.validation_result_factory: ValidationResultFactory = validation_result_factory

        extra_schemas = [
            "geojson-spec/Feature.json",
            "geojson-spec/Geometry.json",
            "stac-spec/catalog-spec/json-schema/catalog.json",
            "stac-spec/catalog-spec/json-schema/catalog-core.json",
            "stac-spec/collection-spec/json-schema/collection.json",
            "stac-spec/item-spec/json-schema/basics.json",
            "stac-spec/item-spec/json-schema/datetime.json",
            "stac-spec/item-spec/json-schema/instrument.json",
            "stac-spec/item-spec/json-schema/item.json",
            "stac-spec/item-spec/json-schema/licensing.json",
            "stac-spec/item-spec/json-schema/provider.json",
        ]

        uri_dictionary = URIDict()
        for extra_schema in extra_schemas:
            # Normalize URLs the same way as jsonschema does
            schema_dict = self.get_schema_dict(extra_schema)
            self.schema_cache[uri_dictionary.normalize(schema_dict["$id"])] = schema_dict

    def get_schema_dict(self, path: str) -> JsonObject:
        with open(join(self.script_dir, path)) as file_pointer:
            schema_dict: JsonObject = load(file_pointer)
            return schema_dict

    @typing.no_type_check
    def get_schema_from_uri(self, schema_uri):
        if schema_uri not in self.schema_cache:
            s = json.loads(STAC_IO.read_text(schema_uri))
            self.schema_cache[schema_uri] = s

        schema = self.schema_cache[schema_uri]

        resolver = jsonschema.validators.RefResolver(
            base_uri=schema_uri, referrer=schema, store=self.schema_cache
        )

        return (schema, resolver)

    @typing.no_type_check
    def _validate_from_uri(self, stac_dict, schema_uri):
        schema, resolver = self.get_schema_from_uri(schema_uri)
        jsonschema.validate(instance=stac_dict, schema=schema, resolver=resolver)
        for uri in resolver.store:
            if uri not in self.schema_cache:
                self.schema_cache[uri] = resolver.store[uri]

    @typing.no_type_check
    def _get_error_message(self, schema_uri, stac_object_type, extension_id, href, stac_id):
        s = "Validation failed for {} ".format(stac_object_type)
        if href is not None:
            s += "at {} ".format(href)
        if stac_id is not None:
            s += "with ID {} ".format(stac_id)
        s += "against schema at {}".format(schema_uri)
        if extension_id is not None:
            s += " for STAC extension '{}'".format(extension_id)

        return s

    @typing.no_type_check
    def validate_core(self, stac_dict, stac_object_type, stac_version, href=None):
        """Validate a core stac object.

        Return value can be None or specific to the implementation.

        Args:
            stac_dict (dict): Dictionary that is the STAC json of the object.
            stac_object_type (str): The stac object type of the object encoded in stac_dict.
                One of :class:`~pystac.STACObjectType`.
            stac_version (str): The version of STAC to validate the object against.
            href (str): Optional HREF of the STAC object being validated.

        Returns:
           str: URI for the JSON schema that was validated against, or None if
               no validation occurred.
        """

        schema_uri = self.schema_uri_map.get_core_schema_uri(stac_object_type, stac_version)

        if schema_uri is None:
            return None

        try:
            self._validate_from_uri(stac_dict, schema_uri)
        except jsonschema.exceptions.ValidationError as e:
            msg = self._get_error_message(
                schema_uri, stac_object_type, None, href, stac_dict.get("id")
            )
            raise STACValidationError(msg, source=e) from e

        if href:
            self.dataset_metadata.append({"url": href})

        if stac_object_type == STACObjectType.ITEM:
            item = Item.from_dict(stac_dict)
            for asset in item.get_assets():
                asset_dict = {
                    "url": asset.get_absolute_href,
                    "multihash": asset.properties["file:checksum"],
                }
                self.dataset_assets.append(asset_dict)

        elif stac_object_type == STACObjectType.COLLECTION:
            collection = Collection.from_dict(stac_dict)
            if "assets" in collection.extra_fields:
                for asset, asset_keys in collection.extra_fields["assets"].items():
                    asset_dict = {
                        "url": asset_keys["href"],
                        "multihash": asset_keys["file:checksum"],
                    }
                    self.dataset_assets.append(asset_dict)

        return schema_uri

    @typing.no_type_check
    def validate_extension(
        self, stac_dict, stac_object_type, stac_version, extension_id, href=None
    ):
        """Validate an extension stac object.

        Return value can be None or specific to the implementation.

        Args:
            stac_dict (dict): Dictionary that is the STAC json of the object.
            stac_object_type (str): The stac object type of the object encoded in stac_dict.
                One of :class:`~pystac.STACObjectType`.
            stac_version (str): The version of STAC to validate the object against.
            extension_id (str): The extension ID to validate against.
            href (str): Optional HREF of the STAC object being validated.

        Returns:
           str: URI for the JSON schema that was validated against, or None if
               no validation occurred.
        """
        schema_uri = self.schema_uri_map.get_extension_schema_uri(
            extension_id, stac_object_type, stac_version
        )

        if schema_uri is None:
            return None

        try:
            self._validate_from_uri(stac_dict, schema_uri)
            return schema_uri
        except jsonschema.exceptions.ValidationError as e:
            msg = self._get_error_message(
                schema_uri, stac_object_type, extension_id, href, stac_dict.get("id")
            )
            raise STACValidationError(msg, source=e) from e
