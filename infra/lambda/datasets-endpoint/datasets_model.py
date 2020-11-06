"""Dataset object DynamoDB model."""

import uuid
from datetime import datetime, timezone

from pynamodb.attributes import UTCDateTimeAttribute, UnicodeAttribute
from pynamodb.indexes import AllProjection, GlobalSecondaryIndex
from pynamodb.models import Model


class DatasetsTitleIdx(GlobalSecondaryIndex):
    """Dataset type/title global index."""

    class Meta:  # pylint:disable=too-few-public-methods
        """Meta class."""

        index_name = "datasets_title"
        read_capacity_units = 1
        write_capacity_units = 1
        projection = AllProjection()

    type = UnicodeAttribute(hash_key=True, attr_name="sk")
    title = UnicodeAttribute(range_key=True)


class DatasetsOwningGroupIdx(GlobalSecondaryIndex):
    """Dataset type/owning_group global index."""

    class Meta:  # pylint:disable=too-few-public-methods
        """Meta class."""

        index_name = "datasets_owning_group"
        read_capacity_units = 1
        write_capacity_units = 1
        projection = AllProjection()

    type = UnicodeAttribute(hash_key=True, attr_name="sk")
    owning_group = UnicodeAttribute(range_key=True)


class DatasetModel(Model):
    """Dataset model."""

    class Meta:  # pylint:disable=too-few-public-methods
        """Meta class."""

        table_name = "datasets"
        region = "ap-southeast-2"  # TODO: don't hardcode region

    id = UnicodeAttribute(
        hash_key=True, attr_name="pk", default=f"DATASET#{uuid.uuid1().hex}", null=False
    )
    type = UnicodeAttribute(range_key=True, attr_name="sk", null=False)
    title = UnicodeAttribute(null=False)
    owning_group = UnicodeAttribute(null=False)
    created_at = UTCDateTimeAttribute(null=False, default=datetime.now(timezone.utc))
    updated_at = UTCDateTimeAttribute()

    datasets_tile_idx = DatasetsTitleIdx()
    datasets_owning_group_idx = DatasetsOwningGroupIdx()

    def save(
        self, conditional_operator=None, **expected_values
    ):  # pylint:disable=unused-argument,arguments-differ
        self.updated_at = datetime.now(timezone.utc)
        super(DatasetModel, self).save()  # pylint:disable=super-with-arguments

    @property
    def dataset_id(self):
        """Dataset ID value."""
        return self.id.split("#")[1]

    @property
    def dataset_type(self):
        """Dataset type value."""
        return self.type.split("#")[1]

    def __iter__(self):
        for name, attr in self.get_attributes().items():
            yield name, attr.serialize(getattr(self, name))
