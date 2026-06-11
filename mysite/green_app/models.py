# coding: utf-8
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class UserProfile(AbstractUser):
    """Профиль пользователя (родитель или администратор)"""

    class Role(models.TextChoices):
        PARENT = 'parent', 'Родитель'
        ADMIN = 'admin', 'Администратор'

    email = models.EmailField(unique=True, verbose_name='Email')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='Аватар')
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.PARENT, verbose_name='Роль'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self):
        return f'{self.email} ({self.get_role_display()})'


class ChildProfile(models.Model):
    """Профиль ребёнка"""
    parent = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE,
        related_name='children', verbose_name='Родитель'
    )
    name = models.CharField(max_length=100, verbose_name='Имя')
    age = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2), MaxValueValidator(10)],
        verbose_name='Возраст'
    )
    avatar = models.ImageField(upload_to='children/', null=True, blank=True, verbose_name='Аватар')
    total_points = models.PositiveIntegerField(default=0, verbose_name='Всего баллов')
    level = models.PositiveSmallIntegerField(default=1, verbose_name='Уровень')
    streak_days = models.PositiveSmallIntegerField(default=0, verbose_name='Серия дней')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        verbose_name = 'Профиль ребёнка'
        verbose_name_plural = 'Профили детей'

    def __str__(self):
        return f'{self.name} (возраст {self.age}, уровень {self.level})'


class MissionCategory(models.Model):
    """Категория заданий"""
    name = models.CharField(max_length=100, verbose_name='Название')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    description = models.TextField(blank=True, verbose_name='Описание')
    icon = models.CharField(max_length=100, blank=True, verbose_name='Иконка')

    class Meta:
        verbose_name = 'Категория заданий'
        verbose_name_plural = 'Категории заданий'

    def __str__(self):
        return self.name


class Mission(models.Model):
    """Задание"""

    class Difficulty(models.TextChoices):
        EASY = 'easy', 'Лёгкий'
        MEDIUM = 'medium', 'Средний'
        HARD = 'hard', 'Сложный'

    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(verbose_name='Описание')
    category = models.ForeignKey(
        MissionCategory, on_delete=models.SET_NULL,
        null=True, related_name='missions', verbose_name='Категория'
    )
    points = models.PositiveIntegerField(verbose_name='Баллы')
    difficulty = models.CharField(
        max_length=10, choices=Difficulty.choices, default=Difficulty.EASY, verbose_name='Сложность'
    )
    min_age = models.PositiveSmallIntegerField(
        default=2, validators=[MinValueValidator(2), MaxValueValidator(10)],
        verbose_name='Минимальный возраст'
    )
    max_age = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(2), MaxValueValidator(10)],
        verbose_name='Максимальный возраст'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активно')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        verbose_name = 'Задание'
        verbose_name_plural = 'Задания'

    def __str__(self):
        return self.title


class MissionSubmission(models.Model):
    """Выполненное задание"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'На проверке'
        APPROVED = 'approved', 'Одобрено'
        REJECTED = 'rejected', 'Отклонено'
        AI_REVIEW = 'ai_review', 'AI проверка'

    child = models.ForeignKey(
        ChildProfile, on_delete=models.CASCADE,
        related_name='submissions', verbose_name='Ребёнок'
    )
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE,
        related_name='submissions', verbose_name='Задание'
    )
    parent = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE,
        related_name='submissions', verbose_name='Родитель'
    )
    photo = models.ImageField(
        upload_to='submissions/', null=True, blank=True, verbose_name='Фото'
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING, verbose_name='Статус'
    )
    ai_result = models.TextField(blank=True, verbose_name='Результат AI')
    ai_feedback = models.TextField(blank=True, verbose_name='Обратная связь AI')
    ai_confidence = models.FloatField(null=True, blank=True, verbose_name='Уверенность AI')
    points_awarded = models.PositiveIntegerField(default=0, verbose_name='Начислено баллов')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='Проверено')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        verbose_name = 'Выполненное задание'
        verbose_name_plural = 'Выполненные задания'

    def __str__(self):
        return f'{self.child.name} — {self.mission.title} ({self.get_status_display()})'


class Achievement(models.Model):
    """Достижение"""
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(verbose_name='Описание')
    icon = models.CharField(max_length=100, blank=True, verbose_name='Иконка')
    required_points = models.PositiveIntegerField(default=0, verbose_name='Требуемые баллы')
    required_missions_count = models.PositiveIntegerField(
        default=0, verbose_name='Требуемое кол-во заданий'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активно')

    class Meta:
        verbose_name = 'Достижение'
        verbose_name_plural = 'Достижения'

    def __str__(self):
        return self.title


class ChildAchievement(models.Model):
    """Разблокированное достижение ребёнка"""
    child = models.ForeignKey(
        ChildProfile, on_delete=models.CASCADE,
        related_name='child_achievements', verbose_name='Ребёнок'
    )
    achievement = models.ForeignKey(
        Achievement, on_delete=models.CASCADE,
        related_name='child_achievements', verbose_name='Достижение'
    )
    unlocked_at = models.DateTimeField(auto_now_add=True, verbose_name='Разблокировано')

    class Meta:
        unique_together = ('child', 'achievement')
        verbose_name = 'Достижение ребёнка'
        verbose_name_plural = 'Достижения детей'

    def __str__(self):
        return f'{self.child.name} — {self.achievement.title}'


class AIChatMessage(models.Model):
    """Сообщение AI-чата"""

    class Role(models.TextChoices):
        USER = 'user', 'Пользователь'
        ASSISTANT = 'assistant', 'Ассистент'

    parent = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE,
        related_name='chat_messages', verbose_name='Родитель'
    )
    child = models.ForeignKey(
        ChildProfile, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='chat_messages', verbose_name='Ребёнок'
    )
    role = models.CharField(
        max_length=10, choices=Role.choices, verbose_name='Роль'
    )
    message = models.TextField(verbose_name='Сообщение')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        verbose_name = 'Сообщение чата'
        verbose_name_plural = 'Сообщения чата'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.parent.email} [{self.role}] {self.created_at:%Y-%m-%d %H:%M}'