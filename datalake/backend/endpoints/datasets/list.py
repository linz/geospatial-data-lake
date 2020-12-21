"""List all datasets function."""

from ..utils import success_response
from .model import DatasetModel
from .serializer import serialize_dataset


def list_datasets():
    """GET: List all Datasets."""

    # list all datasets
    datasets = DatasetModel.scan(
        filter_condition=DatasetModel.id.startswith("DATASET#")
        & DatasetModel.type.startswith("TYPE#")
    )

    # return response
    resp_body = []
    for dataset in datasets:
        resp_item = serialize_dataset(dataset)
        resp_body.append(resp_item)

    return success_response(200, resp_body)