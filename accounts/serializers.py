"""Serializers de conta: só formato e validação de entrada."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Cadastro público. `role` é somente leitura: todo cadastro nasce `user` (default do model).

    Unicidade de `username` e `email` vem dos validadores gerados a partir do model.
    """

    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "role"]
        read_only_fields = ["id", "role"]

    def validate(self, attrs):
        # Validadores de AUTH_PASSWORD_VALIDATORS; o usuário (não salvo) permite checar
        # similaridade da senha com username/e-mail.
        candidate = User(username=attrs["username"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        # create_user aplica o hash (Argon2, ver PASSWORD_HASHERS).
        return User.objects.create_user(**validated_data)
