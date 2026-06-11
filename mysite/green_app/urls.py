# coding: utf-8
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView, LoginView, LogoutView, MeView,
    ChildProfileViewSet, MissionCategoryViewSet, MissionViewSet,
    MissionSubmissionViewSet, AchievementViewSet,
    DashboardView, AIChatView,
    ChildStatsView, FamilyStatsView,
)

router = DefaultRouter()
router.register(r'children', ChildProfileViewSet, basename='children')
router.register(r'categories', MissionCategoryViewSet, basename='categories')
router.register(r'missions', MissionViewSet, basename='missions')
router.register(r'submissions', MissionSubmissionViewSet, basename='submissions')
router.register(r'achievements', AchievementViewSet, basename='achievements')

urlpatterns = [
    # Авторизация
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', MeView.as_view(), name='me'),

    # Дашборд и чат
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('ai-chat/', AIChatView.as_view(), name='ai-chat'),

    # Статистика
    path('stats/child/<int:child_id>/', ChildStatsView.as_view(), name='stats-child'),
    path('stats/family/', FamilyStatsView.as_view(), name='stats-family'),

    # ViewSet роуты
    path('', include(router.urls)),
]