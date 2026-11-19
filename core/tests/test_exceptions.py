from rest_framework.exceptions import NotAuthenticated, ValidationError

from core.exceptions import BusinessRuleError, api_exception_handler


def test_business_rule_error_uses_standard_format_and_custom_status():
    exc = BusinessRuleError("room_unavailable", "Horário já reservado.", status_code=409)
    response = api_exception_handler(exc, {})
    assert response.status_code == 409
    assert response.data == {
        "error": {"code": "room_unavailable", "message": "Horário já reservado.", "details": {}}
    }


def test_business_rule_error_defaults_to_422():
    response = api_exception_handler(BusinessRuleError("past", "No passado."), {})
    assert response.status_code == 422


def test_validation_error_keeps_field_details():
    response = api_exception_handler(ValidationError({"start_at": ["Obrigatório."]}), {})
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert "start_at" in response.data["error"]["details"]


def test_drf_exceptions_are_wrapped():
    response = api_exception_handler(NotAuthenticated(), {})
    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"
