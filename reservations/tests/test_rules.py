"""Testes unitários das regras puras (R2, R3, R4, R6).

Sem banco e sem relógio: `now` é fixo e passado por argumento.
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.exceptions import BusinessRuleError
from reservations.rules import BUSINESS_TZ, validate_cancellation, validate_time_window

NOW = datetime(2030, 1, 9, 12, 0, tzinfo=BUSINESS_TZ)


def local(hour: int, minute: int = 0, day: int = 10) -> datetime:
    """Data/hora no fuso de negócio, em janeiro de 2030 (futuro em relação a NOW)."""
    return datetime(2030, 1, day, hour, minute, tzinfo=BUSINESS_TZ)


class TestValidateTimeWindow:
    @pytest.mark.parametrize(
        ("start_at", "end_at"),
        [
            pytest.param(local(9), local(10), id="caso-comum"),
            pytest.param(local(9), local(9, 30), id="R3-exatamente-30min"),
            pytest.param(local(9), local(13), id="R3-exatamente-4h"),
            pytest.param(local(7), local(8), id="R4-comeca-07h00"),
            pytest.param(local(19), local(20), id="R4-termina-20h00"),
            pytest.param(
                datetime(2030, 1, 10, 12, tzinfo=UTC),
                datetime(2030, 1, 10, 13, tzinfo=UTC),
                id="R4-entrada-em-UTC-equivale-a-09h-local",
            ),
        ],
    )
    def test_accepts_valid_window(self, start_at, end_at):
        validate_time_window(start_at, end_at, NOW)

    @pytest.mark.parametrize(
        ("start_at", "end_at", "expected_code"),
        [
            pytest.param(NOW, NOW + timedelta(hours=1), "start_in_past", id="R2-comeca-agora"),
            pytest.param(local(9, day=8), local(10, day=8), "start_in_past", id="R2-dia-anterior"),
            pytest.param(local(9), local(9, 29), "invalid_duration", id="R3-29min"),
            pytest.param(local(9), local(13, 1), "invalid_duration", id="R3-4h01"),
            pytest.param(local(9), local(9), "invalid_duration", id="R3-fim-igual-inicio"),
            pytest.param(local(10), local(9), "invalid_duration", id="R3-fim-antes-do-inicio"),
            pytest.param(local(6, 59), local(8), "outside_business_hours", id="R4-comeca-06h59"),
            pytest.param(local(19), local(20, 1), "outside_business_hours", id="R4-termina-20h01"),
            pytest.param(
                local(22), local(1, day=11), "outside_business_hours", id="R4-virada-de-dia"
            ),
            pytest.param(
                datetime(2030, 1, 10, 9, tzinfo=UTC),
                datetime(2030, 1, 10, 10, tzinfo=UTC),
                "outside_business_hours",
                id="R4-entrada-em-UTC-equivale-a-06h-local",
            ),
        ],
    )
    def test_rejects_invalid_window(self, start_at, end_at, expected_code):
        with pytest.raises(BusinessRuleError) as exc_info:
            validate_time_window(start_at, end_at, NOW)
        assert exc_info.value.error_code == expected_code
        assert exc_info.value.status_code == 422

    def test_past_is_checked_before_duration(self):
        """Ordem definida na spec: com R2 e R3 violadas, devolve R2."""
        with pytest.raises(BusinessRuleError) as exc_info:
            validate_time_window(local(9, day=8), local(9, day=8), NOW)
        assert exc_info.value.error_code == "start_in_past"


class TestValidateCancellation:
    @pytest.mark.parametrize(
        "notice",
        [
            pytest.param(timedelta(hours=2), id="2h-antes"),
            pytest.param(timedelta(hours=1), id="exatamente-1h"),
        ],
    )
    def test_accepts_with_enough_notice(self, notice):
        validate_cancellation(NOW + notice, NOW)

    @pytest.mark.parametrize(
        "notice",
        [
            pytest.param(timedelta(minutes=59), id="59min-antes"),
            pytest.param(timedelta(0), id="no-inicio"),
            pytest.param(-timedelta(minutes=10), id="em-andamento"),
        ],
    )
    def test_rejects_with_short_notice(self, notice):
        with pytest.raises(BusinessRuleError) as exc_info:
            validate_cancellation(NOW + notice, NOW)
        assert exc_info.value.error_code == "cancellation_too_late"
        assert exc_info.value.status_code == 422
