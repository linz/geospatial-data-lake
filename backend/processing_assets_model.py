"""Dataset object DynamoDB model."""

from pynamodb.attributes import UnicodeAttribute
from pynamodb.models import Model

from .resources import ResourceName


class ProcessingAssetsModel(Model):
    class Meta:  # pylint:disable=too-few-public-methods
        table_name = ResourceName.PROCESSING_ASSETS_TABLE_NAME.value
        region = "ap-southeast-2"  # TODO: don't hardcode region

    pk = UnicodeAttribute(hash_key=True)
    sk = UnicodeAttribute(range_key=True)
    url = UnicodeAttribute()
    multihash = UnicodeAttribute(null=True)