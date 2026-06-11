# coding: utf-8
from rest_framework.permissions import BasePermission

from .models import UserProfile


class IsParent(BasePermission):
    """Только авторизованные родители."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == UserProfile.Role.PARENT
        )


class IsAdminUser(BasePermission):
    """Только администраторы."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == UserProfile.Role.ADMIN
        )


class IsParentOfChild(BasePermission):
    """Родитель может управлять только своими детьми."""
    def has_object_permission(self, request, view, obj):
        return obj.parent == request.user


class IsParentOfSubmission(BasePermission):
    """Родитель может видеть только свои submission-записи."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return obj.parent == request.user