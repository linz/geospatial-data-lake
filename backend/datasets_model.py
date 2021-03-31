import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pynamodb.attributes import UTCDateTimeAttribute, UnicodeAttribute
from pynamodb.expressions.condition import Condition
from pynamodb.indexes import AllProjection, GlobalSecondaryIndex
from pynamodb.models import Model
from pynamodb.settings import OperationSettings

from .resources import ResourceName


# TODO: Remove inherit-non-class when https://github.com/PyCQA/pylint/issues/3950 is fixed
class DatasetsTitleIdx(
    GlobalSecondaryIndex["DatasetsModel"]
):  # pylint:disable=too-few-public-methods,inherit-non-class
    """Dataset type/title global index."""

    class Meta:  # pylint:disable=too-few-public-methods
        """Meta class."""

        index_name = "datasets_title"
        read_capacity_units = 1
        write_capacity_units = 1
        projection = AllProjection()

    type = UnicodeAttribute(hash_key=True, attr_name="sk")
    title = UnicodeAttribute(range_key=True)


# TODO: Remove inherit-non-class when https://github.com/PyCQA/pylint/issues/3950 is fixed
class DatasetsOwningGroupIdx(
    GlobalSecondaryIndex["DatasetsModel"]
):  # pylint:disable=too-few-public-methods,inherit-non-class
    """Dataset type/owning_group global index."""

    class Meta:  # pylint:disable=too-few-public-methods
        """Meta class."""

        index_name = "datasets_owning_group"
        read_capacity_units = 1
        write_capacity_units = 1
        projection = AllProjection()

    type = UnicodeAttribute(hash_key=True, attr_name="sk")
    owning_group = UnicodeAttribute(range_key=True)


class DatasetsModel(Model):
    """Dataset model."""

    class Meta:  # pylint:disable=too-few-public-methods
        """Meta class."""

        table_name = ResourceName.DATASETS_TABLE_NAME.value
        region = "ap-southeast-2"  # TODO: don't hardcode region

    id = UnicodeAttribute(
        hash_key=True, attr_name="pk", default=f"DATASET#{uuid.uuid1().hex}", null=False
    )
    type = UnicodeAttribute(range_key=True, attr_name="sk", null=False)
    title = UnicodeAttribute(null=False)
    owning_group = UnicodeAttribute(null=False)
    created_at = UTCDateTimeAttribute(null=False, default=datetime.now(timezone.utc))
    updated_at = UTCDateTimeAttribute()

    datasets_title_idx = DatasetsTitleIdx()
    datasets_owning_group_idx = DatasetsOwningGroupIdx()

    def save(
        self,
        condition: Optional[Condition] = None,
        settings: OperationSettings = OperationSettings.default,
    ) -> Dict[str, Any]:
        self.updated_at = datetime.now(timezone.utc)
        return super().save(condition, settings)

    def as_dict(self) -> Dict[str, Any]:
        serialized = self.serialize()
        result: Dict[str, Any] = {key: value["S"] for key, value in serialized.items()}
        result["id"] = self.dataset_id
        result["type"] = self.dataset_type
        return result

    @property
    def dataset_id(self) -> str:
        """Dataset ID value."""
        return str(self.id).split("#")[1]

    @property
    def dataset_type(self) -> str:
        """Dataset type value."""
        return str(self.type).split("#")[1]