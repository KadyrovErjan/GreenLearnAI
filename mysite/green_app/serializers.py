# coding: utf-8
from rest_framework import serializers
from django.db.models import Sum
from .models import (
    UserProfile, ChildProfile, MissionCategory, Mission,
    MissionSubmission, Achievement, ChildAchievement, AIChatMessage,
    Reward, RewardRedemption, VoiceDiaryEntry, Certificate
)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ('id', 'email', 'username', 'avatar', 'role', 'created_at')
        read_only_fields = ('id', 'created_at', 'role')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = UserProfile
        fields = ('email', 'username', 'password', 'password2')

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password2': 'Пароли не совпадают.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        return UserProfile.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=validated_data['password'],
        )


class ChildProfileSerializer(serializers.ModelSerializer):
    parent = serializers.HiddenField(default=serializers.CurrentUserDefault())

    points_balance = serializers.IntegerField(read_only=True)

    class Meta:
        model = ChildProfile
        fields = (
            'id', 'parent', 'name', 'age', 'avatar',
            'total_points', 'spent_points', 'points_balance',
            'level', 'streak_days', 'created_at'
        )
        read_only_fields = (
            'id', 'total_points', 'spent_points', 'points_balance',
            'level', 'streak_days', 'created_at'
        )


class MissionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MissionCategory
        fields = ('id', 'name', 'slug', 'description', 'icon')


class MissionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Mission
        fields = (
            'id', 'title', 'description', 'category', 'category_name',
            'points', 'difficulty', 'min_age', 'max_age', 'is_active', 'created_at'
        )


class MissionSubmissionSerializer(serializers.ModelSerializer):
    mission_title = serializers.CharField(source='mission.title', read_only=True)
    child_name = serializers.CharField(source='child.name', read_only=True)

    class Meta:
        model = MissionSubmission
        fields = (
            'id', 'child', 'child_name', 'mission', 'mission_title',
            'parent', 'photo', 'status', 'ai_feedback', 'ai_confidence',
            'points_awarded', 'reviewed_at', 'created_at'
        )
        read_only_fields = (
            'id', 'parent', 'status', 'ai_feedback', 'ai_confidence',
            'points_awarded', 'reviewed_at', 'created_at'
        )


class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = (
            'id', 'title', 'description', 'icon',
            'required_points', 'required_missions_count', 'is_active'
        )


class ChildAchievementSerializer(serializers.ModelSerializer):
    achievement = AchievementSerializer(read_only=True)

    class Meta:
        model = ChildAchievement
        fields = ('id', 'child', 'achievement', 'unlocked_at')


class AIChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIChatMessage
        fields = ('id', 'role', 'message', 'created_at')


class RewardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reward
        fields = (
            'id', 'title', 'description', 'partner', 'icon',
            'cost_points', 'stock', 'is_active'
        )


class RewardRedemptionSerializer(serializers.ModelSerializer):
    reward = RewardSerializer(read_only=True)
    child_name = serializers.CharField(source='child.name', read_only=True)

    class Meta:
        model = RewardRedemption
        fields = ('id', 'child', 'child_name', 'reward', 'points_spent', 'code', 'created_at')


class VoiceDiaryEntrySerializer(serializers.ModelSerializer):
    child_name = serializers.CharField(source='child.name', read_only=True)

    class Meta:
        model = VoiceDiaryEntry
        fields = ('id', 'child', 'child_name', 'text', 'word_count', 'ai_feedback', 'created_at')
        read_only_fields = ('id', 'word_count', 'ai_feedback', 'created_at')


class CertificateSerializer(serializers.ModelSerializer):
    child_name = serializers.CharField(source='child.name', read_only=True)

    class Meta:
        model = Certificate
        fields = ('id', 'child', 'child_name', 'code', 'title', 'description', 'icon', 'issued_at')


# ──────────────────────────────────────────────
# Статистика
# ──────────────────────────────────────────────

class ChildStatsSerializer(serializers.Serializer):
    """Статистика одного ребёнка."""
    child = ChildProfileSerializer()
    total_submissions = serializers.IntegerField()
    approved_submissions = serializers.IntegerField()
    rejected_submissions = serializers.IntegerField()
    pending_submissions = serializers.IntegerField()
    total_points = serializers.IntegerField()
    current_level = serializers.IntegerField()
    streak_days = serializers.IntegerField()
    achievements_count = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    submissions_by_category = serializers.DictField(child=serializers.IntegerField())
    points_by_week = serializers.ListField(child=serializers.DictField())
    favorite_category = serializers.CharField(allow_null=True)


class FamilyStatsSerializer(serializers.Serializer):
    """Суммарная статистика по всем детям родителя."""
    total_children = serializers.IntegerField()
    total_points = serializers.IntegerField()
    total_submissions = serializers.IntegerField()
    approved_submissions = serializers.IntegerField()
    total_achievements = serializers.IntegerField()
    children = ChildStatsSerializer(many=True)