"""Erros de domínio e formato padronizado de erro da API.

Toda resposta de erro segue o formato:

    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.views import exception_handler


class BusinessRuleError(APIException):
    """Violação de regra de negócio (R1–R7).

    Padrão 422: a entrada é válida em formato, mas viola uma regra.
    Use status=409 para conflitos de estado (sobreposição, limite de reservas).
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "business_rule_violation"
    default_detail = "Regra de negócio violada."

    def __init__(self, code: str, message: str, status_code: int | None = None, details=None):
        super().__init__(detail=message, code=code)
        self.error_code = code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code


def api_exception_handler(exc, context):
    # Http404 (get_object_or_404 / get_object) traz mensagem do Django em inglês e com o nome
    # do model ("No Reservation matches..."). Usa a mensagem padrão do NotFound do DRF.
    if isinstance(exc, Http404):
        exc = NotFound()

    response = exception_handler(exc, context)
    if response is None:
        # Exceção não tratada: o Django devolve 500 normalmente.
        return None

    if isinstance(exc, BusinessRuleError):
        code, message, details = exc.error_code, str(exc.detail), exc.details
    elif isinstance(exc, ValidationError):
        code, message, details = "validation_error", "Dados inválidos.", response.data
    else:
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else ""
        code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
        message, details = str(detail) or str(exc), {}

    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
