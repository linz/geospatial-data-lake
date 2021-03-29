"""Get datasets functions."""

from jsonschema import ValidationError, validate  # type: ignore[import]
from pynamodb.exceptions import DoesNotExist

from ..api_responses import error_response, success_response
from ..dataset import DATASET_TYPES
from ..datasets_model import datasets_model_with_meta
from ..types import JsonObject
from .list import list_datasets


def handle_get(event: JsonObject) -> JsonObject:
    if "id" in event["body"] and "type" in event["body"]:
        return get_dataset_single(event)

    if "title" in event["body"] or "owning_group" in event["body"]:
        return get_dataset_filter(event)

    if event["body"] == {}:
        return list_datasets()

    return error_response(400, "Unhandled request")


def get_dataset_single(payload: JsonObject) -> JsonObject:
    """GET: Get single Dataset."""

    body_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "type": {
                "type": "string",
                "enum": DATASET_TYPES,
            },
        },
        "required": ["id", "type"],
    }

    # request body validation
    req_body = payload["body"]
    try:
        validate(req_body, body_schema)
    except ValidationError as err:
        return error_response(400, err.message)

    datasets_model_class = datasets_model_with_meta()

    # get dataset
    try:
        dataset = datasets_model_class.get(
            hash_key=f"DATASET#{req_body['id']}",
            range_key=f"TYPE#{req_body['type']}",
            consistent_read=True,
        )
    except DoesNotExist:
        return error_response(
            404, f"dataset '{req_body['id']}' of type '{req_body['type']}' does not exist"
        )

    # return response
    resp_body = dataset.as_dict()

    return success_response(200, resp_body)


def get_dataset_filter(payload: JsonObject) -> JsonObject:
    """GET: Get Datasets by filter."""

    body_schema = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": DATASET_TYPES,
            },
            "title": {"type": "string"},
            "owning_group": {"type": "string"},
        },
        "required": ["type"],
        "minProperties": 2,
        "maxProperties": 2,
    }

    # request body validation
    req_body = payload["body"]
    try:
        validate(req_body, body_schema)
    except ValidationError as err:
        return error_response(400, err.message)

    # dataset query by filter
    datasets_model_class = datasets_model_with_meta()
    if "title" in req_body:
        datasets = datasets_model_class.datasets_title_idx.query(  # pylint:disable=no-member
            hash_key=f"TYPE#{req_body['type']}",
            range_key_condition=datasets_model_class.title == req_body["title"],
        )

    if "owning_group" in req_body:
        datasets = datasets_model_class.datasets_owning_group_idx.query(  # pylint:disable=no-member
            hash_key=f"TYPE#{req_body['type']}",
            range_key_condition=datasets_model_class.owning_group == req_body["owning_group"],
        )

    # return response
    resp_body = []
    for dataset in datasets:
        resp_item = dataset.as_dict()
        resp_body.append(resp_item)

    return success_response(200, resp_body)
