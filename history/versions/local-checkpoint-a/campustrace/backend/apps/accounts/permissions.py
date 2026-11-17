from rest_framework.permissions import BasePermission

from .models import User


class IsManagementUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.role in {User.Role.STAFF, User.Role.ADMIN})


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.role == User.Role.ADMIN)
