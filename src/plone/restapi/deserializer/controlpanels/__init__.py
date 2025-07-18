from plone.dexterity.interfaces import IDexterityContent
from plone.registry.interfaces import IRegistry
from plone.restapi.controlpanels import IControlpanel
from plone.restapi.deserializer import json_body
from plone.restapi.interfaces import IDeserializeFromJson
from plone.restapi.interfaces import IFieldDeserializer
from z3c.form.interfaces import IManagerValidator
from zExceptions import BadRequest
from zope.component import adapter
from zope.component import getUtility
from zope.component import queryMultiAdapter
from zope.i18n import translate
from zope.interface import implementer
from zope.interface.exceptions import Invalid
from zope.schema import getFields
from zope.schema.interfaces import ValidationError


@implementer(IDexterityContent)
class FakeDXContext:
    """Fake DX content class, so we can reuse the DX field deserializers"""


@implementer(IDeserializeFromJson)
@adapter(IControlpanel)
class ControlpanelDeserializeFromJson:
    def __init__(self, controlpanel):
        self.controlpanel = controlpanel
        self.schema = self.controlpanel.schema
        self.schema_prefix = self.controlpanel.schema_prefix

        self.registry = getUtility(IRegistry)

        self.context = self.controlpanel.context
        self.request = self.controlpanel.request

    def __call__(self, mask_validation_errors=True):
        if self.schema is None:
            return

        data = json_body(self.controlpanel.request)

        proxy = self.registry.forInterface(self.schema, prefix=self.schema_prefix)

        schema_data = {}
        errors = []

        # Make a fake context
        fake_context = FakeDXContext()

        for name, field in getFields(self.schema).items():
            field_data = schema_data.setdefault(self.schema, {})

            if field.readonly:
                continue

            if name in data:
                deserializer = queryMultiAdapter(
                    (field, fake_context, self.request), IFieldDeserializer
                )

                try:
                    # Make it sane
                    value = deserializer(data[name])
                    # Validate required etc
                    field.validate(value)
                    # Set the value.
                    setattr(proxy, name, value)
                except ValidationError as e:
                    errors.append({"message": e.doc(), "field": name, "error": e})
                except (ValueError, Invalid) as e:
                    errors.append({"message": str(e), "field": name, "error": e})
                else:
                    field_data[name] = value

        # Validate schemata
        for schema, field_data in schema_data.items():
            validator = queryMultiAdapter(
                (self.context, self.request, None, schema, None), IManagerValidator
            )
            for error in validator.validate(field_data):
                errors.append({"error": error, "message": str(error)})

        if errors:
            for error in errors:
                if mask_validation_errors:
                    # Drop Python specific error classes in order to be able to better handle
                    # errors on front-end
                    error["error"] = "ValidationError"
                error["message"] = translate(error["message"], context=self.request)
            raise BadRequest(errors)
