from typing import Any, Optional

from aws_cdk import aws_iam, aws_s3
from aws_cdk.core import Construct, Stack, Tags

from infrastructure.roles import MAX_SESSION_DURATION


class LDSStack(Stack):
    def __init__(
        self,
        scope: Optional[Construct] = None,
        stack_id: Optional[str] = None,
        *,
        deploy_env: str,
        storage_bucket: aws_s3.Bucket,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, stack_id, **kwargs)

        account_principal = aws_iam.AccountPrincipal(account_id=276514628126)
        role = aws_iam.Role(
            self,
            "koordinates-read-role",
            role_name=f"koordinates-s3-access-read-role-{deploy_env}",
            assumed_by=account_principal,  # type: ignore[arg-type]
            external_id={"prod": "koordinates-jAddR"}.get(deploy_env, "koordinates-4BnJQ"),
            max_session_duration=MAX_SESSION_DURATION,
        )
        storage_bucket.grant_read(role)  # type: ignore[arg-type]

        Tags.of(self).add("ApplicationLayer", "lds")  # type: ignore[arg-type]