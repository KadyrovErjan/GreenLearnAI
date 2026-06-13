# coding: utf-8
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    UserProfile, ChildProfile, MissionCategory, Mission,
    MissionSubmission, Achievement, ChildAchievement, AIChatMessage,
    Reward, RewardRedemption, VoiceDiaryEntry, Certificate
)


@admin.register(UserProfile)
class UserProfileAdmin(UserAdmin):
    list_display = ('email', 'username', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('email', 'username')
    ordering = ('-created_at',)
    fieldsets = UserAdmin.fieldsets + (
        ('GreenLearn', {'fields': ('avatar', 'role')}),
    )


@admin.register(ChildProfile)
class ChildProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'age', 'total_points', 'level', 'streak_days')
    list_filter = ('age', 'level')
    search_fields = ('name', 'parent__email')


@admin.register(MissionCategory)
class MissionCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'difficulty', 'points', 'min_age', 'max_age', 'is_active')
    list_filter = ('difficulty', 'is_active', 'category')
    search_fields = ('title',)
    list_editable = ('is_active',)


@admin.register(MissionSubmission)
class MissionSubmissionAdmin(admin.ModelAdmin):
    list_display = ('child', 'mission', 'parent', 'status', 'points_awarded', 'created_at')
    list_filter = ('status',)
    search_fields = ('child__name', 'mission__title', 'parent__email')
    readonly_fields = ('created_at', 'reviewed_at')


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('title', 'required_points', 'required_missions_count', 'is_active')
    list_editable = ('is_active',)


@admin.register(ChildAchievement)
class ChildAchievementAdmin(admin.ModelAdmin):
    list_display = ('child', 'achievement', 'unlocked_at')
    search_fields = ('child__name', 'achievement__title')


@admin.register(AIChatMessage)
class AIChatMessageAdmin(admin.ModelAdmin):
    list_display = ('parent', 'child', 'role', 'created_at')
    list_filter = ('role',)
    search_fields = ('parent__email', 'message')


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ('title', 'partner', 'cost_points', 'stock', 'is_active')
    list_filter = ('is_active', 'partner')
    search_fields = ('title', 'partner')
    list_editable = ('is_active',)


@admin.register(RewardRedemption)
class RewardRedemptionAdmin(admin.ModelAdmin):
    list_display = ('child', 'reward', 'points_spent', 'code', 'created_at')
    search_fields = ('child__name', 'reward__title', 'code')
    readonly_fields = ('created_at',)


@admin.register(VoiceDiaryEntry)
class VoiceDiaryEntryAdmin(admin.ModelAdmin):
    list_display = ('child', 'word_count', 'created_at')
    search_fields = ('child__name', 'text')
    readonly_fields = ('created_at',)


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('child', 'title', 'code', 'issued_at')
    list_filter = ('code',)
    search_fields = ('child__name', 'title')