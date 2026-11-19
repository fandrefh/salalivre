from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminRole(BasePermission):
    """Permite acesso apenas a usuários com role=admin."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin_role)


class IsAdminOrReadOnly(BasePermission):
    """Leitura para qualquer autenticado; escrita só para admin (ex.: salas)."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or user.is_admin_role
