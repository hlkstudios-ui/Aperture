from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.legal_policy_schemas import (
    LegalPolicyAdminResponse,
    LegalPolicyEditable,
    LegalPolicyPutRequest,
)
from app.models import LegalPolicyConfiguration

LEGAL_POLICY_FIELDS = (
    "legal_operator_name",
    "country_code",
    "region",
    "support_email",
    "privacy_email",
    "copyright_email",
    "minimum_user_age",
    "governing_law_jurisdiction",
)


def _empty_values() -> dict[str, object | None]:
    return {field: None for field in LEGAL_POLICY_FIELDS}


def _conflict() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        "Legal policy draft changed; reload and try again",
    )


def admin_response(
    configuration: LegalPolicyConfiguration | None,
) -> LegalPolicyAdminResponse:
    values = (
        {field: getattr(configuration, field) for field in LEGAL_POLICY_FIELDS}
        if configuration is not None
        else _empty_values()
    )
    return LegalPolicyAdminResponse(
        **values,
        revision=configuration.revision if configuration is not None else 0,
        updated_at=configuration.updated_at if configuration is not None else None,
    )


def put_configuration(
    db: Session,
    payload: LegalPolicyPutRequest,
) -> tuple[LegalPolicyConfiguration | None, list[str]]:
    configuration = db.get(LegalPolicyConfiguration, 1, with_for_update=True)
    values = LegalPolicyEditable.model_validate(
        payload.model_dump(exclude={"revision"})
    ).model_dump(mode="json")

    if configuration is None:
        if payload.revision != 0:
            raise _conflict()
        changed_fields = [field for field in LEGAL_POLICY_FIELDS if values[field] is not None]
        if not changed_fields:
            return None, []
        configuration = LegalPolicyConfiguration(
            site_brand_configuration_id=1,
            revision=1,
            **values,
        )
        db.add(configuration)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise _conflict() from None
        return configuration, changed_fields

    if configuration.revision != payload.revision:
        raise _conflict()
    changed_fields = [
        field for field in LEGAL_POLICY_FIELDS if getattr(configuration, field) != values[field]
    ]
    if not changed_fields:
        return configuration, []

    result = db.execute(
        update(LegalPolicyConfiguration)
        .where(
            LegalPolicyConfiguration.site_brand_configuration_id == 1,
            LegalPolicyConfiguration.revision == payload.revision,
        )
        .values(
            **values,
            revision=payload.revision + 1,
            updated_at=datetime.now(UTC),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise _conflict()
    db.flush()
    db.refresh(configuration)
    return configuration, changed_fields
