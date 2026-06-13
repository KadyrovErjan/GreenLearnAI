# coding: utf-8
import logging
from datetime import datetime, timedelta

from django.db.models import Sum, Count
from django.utils import timezone
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    UserProfile, ChildProfile, MissionCategory, Mission,
    MissionSubmission, Achievement, ChildAchievement, AIChatMessage,
    Reward, RewardRedemption, VoiceDiaryEntry, Certificate
)
from .permissions import IsParent, IsAdminUser, IsParentOfChild, IsParentOfSubmission
from .serializers import (
    UserProfileSerializer, RegisterSerializer, ChildProfileSerializer,
    MissionCategorySerializer, MissionSerializer, MissionSubmissionSerializer,
    AchievementSerializer, ChildAchievementSerializer, AIChatMessageSerializer,
    ChildStatsSerializer, FamilyStatsSerializer,
    RewardSerializer, RewardRedemptionSerializer,
    VoiceDiaryEntrySerializer, CertificateSerializer
)
from .services.gamification import award_points, update_streak, unlock_achievements
from .services.missions import can_submit_today, get_recommended_missions
from .services.ai_chat import chat_with_ai, analyze_diary_entry, get_persona
from .services.ai_vision import check_mission_photo
from .services.certificates import check_and_issue_certificates

logger = logging.getLogger('green_app')


# ──────────────────────────────────────────────
# Пагинация
# ──────────────────────────────────────────────

class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ──────────────────────────────────────────────
# Авторизация
# ──────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserProfileSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        from django.contrib.auth import authenticate
        email = request.data.get('email', '').lower().strip()
        password = request.data.get('password', '')
        user = authenticate(request, username=email, password=password)
        if not user:
            return Response({'detail': 'Неверный email или пароль.'}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserProfileSerializer(user).data,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass
        return Response({'detail': 'Выход выполнен.'})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


# ──────────────────────────────────────────────
# Дети
# ──────────────────────────────────────────────

class ChildProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ChildProfileSerializer
    permission_classes = [IsParent]
    pagination_class = StandardPagination

    def get_queryset(self):
        return ChildProfile.objects.filter(parent=self.request.user)

    def perform_create(self, serializer):
        serializer.save(parent=self.request.user)


# ──────────────────────────────────────────────
# Категории и задания
# ──────────────────────────────────────────────

class MissionCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MissionCategory.objects.all()
    serializer_class = MissionCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination


class MissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MissionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = Mission.objects.filter(is_active=True).select_related('category')

        category = self.request.query_params.get('category')
        difficulty = self.request.query_params.get('difficulty')
        min_age = self.request.query_params.get('min_age')
        max_age = self.request.query_params.get('max_age')

        if category:
            qs = qs.filter(category__slug=category)
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        if min_age:
            qs = qs.filter(min_age__gte=min_age)
        if max_age:
            qs = qs.filter(max_age__lte=max_age)

        return qs

    @action(detail=False, methods=['get'], url_path='recommended/(?P<child_id>[^/.]+)')
    def recommended(self, request, child_id=None):
        try:
            child = ChildProfile.objects.get(id=child_id, parent=request.user)
        except ChildProfile.DoesNotExist:
            return Response({'detail': 'Ребёнок не найден.'}, status=status.HTTP_404_NOT_FOUND)

        missions = get_recommended_missions(child)
        serializer = self.get_serializer(missions, many=True)
        return Response(serializer.data)


# ──────────────────────────────────────────────
# Выполненные задания
# ──────────────────────────────────────────────

class MissionSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = MissionSubmissionSerializer
    permission_classes = [IsParentOfSubmission]
    pagination_class = StandardPagination
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return MissionSubmission.objects.filter(
            parent=self.request.user
        ).select_related('child', 'mission')

    def perform_create(self, serializer):
        child = serializer.validated_data['child']
        mission = serializer.validated_data['mission']

        if child.parent != self.request.user:
            raise ValidationError('Этот ребёнок не принадлежит вам.')

        if not can_submit_today(child, mission):
            raise ValidationError('Это задание уже было отправлено сегодня.')

        has_photo = 'photo' in self.request.FILES
        initial_status = MissionSubmission.Status.AI_REVIEW if has_photo else MissionSubmission.Status.PENDING

        submission = serializer.save(parent=self.request.user, status=initial_status)

        if has_photo:
            result = check_mission_photo(submission)
            logger.info('perform_create: ai_vision result=%s', result)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        submission = self.get_object()
        if submission.status == MissionSubmission.Status.APPROVED:
            return Response({'detail': 'Уже одобрено.'})

        submission.status = MissionSubmission.Status.APPROVED
        submission.points_awarded = submission.mission.points
        submission.reviewed_at = timezone.now()
        submission.save(update_fields=['status', 'points_awarded', 'reviewed_at'])

        award_points(submission.child, submission.mission.points)
        update_streak(submission.child)
        new_achievements = unlock_achievements(submission.child)

        logger.info(
            'approve: submission=%s child=%s points=%s achievements=%s',
            submission.id, submission.child.name,
            submission.mission.points, len(new_achievements)
        )

        return Response({
            'detail': 'Задание одобрено.',
            'points_awarded': submission.mission.points,
            'new_achievements': [a.title for a in new_achievements],
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        submission = self.get_object()
        reason = request.data.get('reason', '')
        submission.status = MissionSubmission.Status.REJECTED
        submission.ai_feedback = reason
        submission.reviewed_at = timezone.now()
        submission.save(update_fields=['status', 'ai_feedback', 'reviewed_at'])

        logger.info('reject: submission=%s child=%s', submission.id, submission.child.name)

        return Response({'detail': 'Задание отклонено.'})


# ──────────────────────────────────────────────
# Достижения
# ──────────────────────────────────────────────

class AchievementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Achievement.objects.filter(is_active=True)
    serializer_class = AchievementSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination


# ──────────────────────────────────────────────
# Дашборд
# ──────────────────────────────────────────────

class DashboardView(APIView):
    permission_classes = [IsParent]

    def get(self, request):
        children = ChildProfile.objects.filter(parent=request.user)
        data = []
        for child in children:
            pending = MissionSubmission.objects.filter(
                child=child, status=MissionSubmission.Status.PENDING
            ).count()
            achievements = ChildAchievement.objects.filter(child=child).count()
            data.append({
                'child': ChildProfileSerializer(child, context={'request': request}).data,
                'pending_submissions': pending,
                'achievements_count': achievements,
            })
        return Response({'children': data})


# ──────────────────────────────────────────────
# AI-чат
# ──────────────────────────────────────────────

class AIChatView(APIView):
    permission_classes = [IsParent]

    def get(self, request):
        child_id = request.query_params.get('child_id')
        qs = AIChatMessage.objects.filter(parent=request.user)
        if child_id:
            qs = qs.filter(child_id=child_id)
        qs = qs.order_by('-created_at')[:50]
        messages = list(reversed(qs))
        return Response(AIChatMessageSerializer(messages, many=True).data)

    def post(self, request):
        user_message = request.data.get('message', '').strip()
        if not user_message:
            return Response({'detail': 'Сообщение не может быть пустым.'}, status=status.HTTP_400_BAD_REQUEST)

        ai_response = _process_chat_message(request, user_message)
        return Response({'response': ai_response})


def _process_chat_message(request, user_message: str) -> str:
    """Общая логика чата: контекст ребёнка, режим, история, сохранение сообщений."""
    mode = request.data.get('mode', 'assistant')
    if mode not in ('assistant', 'psychologist'):
        mode = 'assistant'

    child_id = request.data.get('child_id')
    child = None
    if child_id:
        try:
            child = ChildProfile.objects.get(id=child_id, parent=request.user)
        except ChildProfile.DoesNotExist:
            pass

    history = list(
        AIChatMessage.objects.filter(parent=request.user)
        .order_by('-created_at')[:20]
    )
    history = list(reversed(history))

    ai_response = chat_with_ai(user_message, history, child=child, mode=mode)

    AIChatMessage.objects.create(
        parent=request.user, child=child, role='user', message=user_message
    )
    AIChatMessage.objects.create(
        parent=request.user, child=child, role='assistant', message=ai_response
    )
    return ai_response


class AIVoiceChatView(APIView):
    """
    Голосовой чат: принимает распознанный текст (transcript) после
    Web Speech API на фронтенде. Возвращает {'text': ответ ИИ, 'transcript': текст пользователя}.
    """
    permission_classes = [IsParent]

    def post(self, request):
        transcript = (request.data.get('transcript') or request.data.get('message') or '').strip()
        if not transcript:
            return Response(
                {'detail': 'Не удалось распознать речь. Попробуйте ещё раз.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ai_response = _process_chat_message(request, transcript)
        return Response({'text': ai_response, 'transcript': transcript})


# ──────────────────────────────────────────────
# Магазин наград (GreenPoints)
# ──────────────────────────────────────────────

class RewardViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RewardSerializer
    permission_classes = [IsParent]
    pagination_class = StandardPagination

    def get_queryset(self):
        return Reward.objects.filter(is_active=True)

    @action(detail=True, methods=['post'])
    def redeem(self, request, pk=None):
        import secrets
        from django.db import transaction

        reward = self.get_object()
        child_id = request.data.get('child_id')
        try:
            child = ChildProfile.objects.get(id=child_id, parent=request.user)
        except ChildProfile.DoesNotExist:
            return Response({'detail': 'Ребёнок не найден.'}, status=status.HTTP_404_NOT_FOUND)

        if reward.stock is not None and reward.stock <= 0:
            return Response({'detail': 'Эта награда закончилась.'}, status=status.HTTP_400_BAD_REQUEST)
        if child.points_balance < reward.cost_points:
            return Response(
                {'detail': f'Недостаточно GreenPoints: нужно {reward.cost_points}, доступно {child.points_balance}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            child.spent_points += reward.cost_points
            child.save(update_fields=['spent_points'])
            if reward.stock is not None:
                reward.stock -= 1
                reward.save(update_fields=['stock'])
            redemption = RewardRedemption.objects.create(
                child=child,
                reward=reward,
                parent=request.user,
                points_spent=reward.cost_points,
                code=f'GL-{secrets.token_hex(4).upper()}',
            )

        logger.info('redeem: child=%s reward=%s code=%s', child.name, reward.title, redemption.code)
        return Response(RewardRedemptionSerializer(redemption).data, status=status.HTTP_201_CREATED)


class RedemptionListView(generics.ListAPIView):
    serializer_class = RewardRedemptionSerializer
    permission_classes = [IsParent]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = RewardRedemption.objects.filter(parent=self.request.user).select_related('reward', 'child')
        child_id = self.request.query_params.get('child_id')
        if child_id:
            qs = qs.filter(child_id=child_id)
        return qs


# ──────────────────────────────────────────────
# Голосовой дневник
# ──────────────────────────────────────────────

class VoiceDiaryView(APIView):
    permission_classes = [IsParent]

    def get(self, request):
        qs = VoiceDiaryEntry.objects.filter(parent=request.user).select_related('child')
        child_id = request.query_params.get('child_id')
        if child_id:
            qs = qs.filter(child_id=child_id)
        entries = qs[:50]
        return Response(VoiceDiaryEntrySerializer(entries, many=True).data)

    def post(self, request):
        text = (request.data.get('text') or '').strip()
        if not text:
            return Response({'detail': 'Запись не может быть пустой.'}, status=status.HTTP_400_BAD_REQUEST)

        child_id = request.data.get('child_id') or request.data.get('child')
        try:
            child = ChildProfile.objects.get(id=child_id, parent=request.user)
        except (ChildProfile.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Ребёнок не найден.'}, status=status.HTTP_404_NOT_FOUND)

        ai_feedback = analyze_diary_entry(text, child)
        entry = VoiceDiaryEntry.objects.create(
            parent=request.user,
            child=child,
            text=text,
            word_count=len(text.split()),
            ai_feedback=ai_feedback,
        )
        return Response(VoiceDiaryEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


# ──────────────────────────────────────────────
# Eco Passport и сертификаты
# ──────────────────────────────────────────────

class EcoPassportView(APIView):
    permission_classes = [IsParent]

    def get(self, request, child_id):
        try:
            child = ChildProfile.objects.get(id=child_id, parent=request.user)
        except ChildProfile.DoesNotExist:
            return Response({'detail': 'Ребёнок не найден.'}, status=status.HTTP_404_NOT_FOUND)

        # Выдать новые сертификаты, если достигнуты пороги
        check_and_issue_certificates(child)

        approved_qs = MissionSubmission.objects.filter(
            child=child, status=MissionSubmission.Status.APPROVED
        )
        by_category = (
            approved_qs.values('mission__category__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        certificates = Certificate.objects.filter(child=child)
        persona = get_persona(child)

        return Response({
            'child': ChildProfileSerializer(child, context={'request': request}).data,
            'persona': {'key': persona['key'], 'name': persona['name']},
            'approved_missions': approved_qs.count(),
            'total_points': child.total_points,
            'points_balance': child.points_balance,
            'streak_days': child.streak_days,
            'achievements_count': ChildAchievement.objects.filter(child=child).count(),
            'diary_entries_count': VoiceDiaryEntry.objects.filter(child=child).count(),
            'by_category': {
                (row['mission__category__name'] or 'Без категории'): row['count']
                for row in by_category
            },
            'certificates': CertificateSerializer(certificates, many=True).data,
        })


class CertificatePDFView(APIView):
    permission_classes = [IsParent]

    def get(self, request, pk):
        from django.http import HttpResponse

        try:
            certificate = Certificate.objects.select_related('child').get(
                pk=pk, child__parent=request.user
            )
        except Certificate.DoesNotExist:
            return Response({'detail': 'Сертификат не найден.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from .services.certificate_pdf import generate_certificate_pdf
            pdf_bytes = generate_certificate_pdf(certificate)
        except ImportError:
            return Response(
                {'detail': 'Генерация PDF недоступна: не установлен reportlab.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="certificate-{certificate.code}-{certificate.id}.pdf"'
        )
        return response


# ──────────────────────────────────────────────
# Статистика
# ──────────────────────────────────────────────

def _build_child_stats(child) -> dict:
    from django.db.models.functions import TruncWeek

    submissions = MissionSubmission.objects.filter(child=child)
    total = submissions.count()
    approved = submissions.filter(status=MissionSubmission.Status.APPROVED).count()
    rejected = submissions.filter(status=MissionSubmission.Status.REJECTED).count()
    pending = submissions.filter(status=MissionSubmission.Status.PENDING).count()
    completion_rate = round((approved / total * 100) if total else 0, 1)

    # Разбивка по категориям
    by_category_qs = (
        submissions.filter(status=MissionSubmission.Status.APPROVED)
        .values('mission__category__name')
        .annotate(cnt=Count('id'))
    )
    by_category = {
        (row['mission__category__name'] or 'Без категории'): row['cnt']
        for row in by_category_qs
    }

    # Любимая категория
    favorite_category = max(by_category, key=by_category.get) if by_category else None

    # Баллы по неделям (последние 8 недель)
    eight_weeks_ago = timezone.now() - timedelta(weeks=8)
    weekly_qs = (
        submissions.filter(
            status=MissionSubmission.Status.APPROVED,
            reviewed_at__gte=eight_weeks_ago
        )
        .annotate(week=TruncWeek('reviewed_at'))
        .values('week')
        .annotate(points=Sum('points_awarded'))
        .order_by('week')
    )
    points_by_week = [
        {'week': row['week'].strftime('%G-W%V'), 'points': row['points'] or 0}
        for row in weekly_qs
    ]

    achievements_count = ChildAchievement.objects.filter(child=child).count()

    return {
        'child': child,
        'total_submissions': total,
        'approved_submissions': approved,
        'rejected_submissions': rejected,
        'pending_submissions': pending,
        'total_points': child.total_points,
        'current_level': child.level,
        'streak_days': child.streak_days,
        'achievements_count': achievements_count,
        'completion_rate': completion_rate,
        'submissions_by_category': by_category,
        'points_by_week': points_by_week,
        'favorite_category': favorite_category,
    }


class ChildStatsView(APIView):
    permission_classes = [IsParent]

    def get(self, request, child_id):
        try:
            child = ChildProfile.objects.get(id=child_id, parent=request.user)
        except ChildProfile.DoesNotExist:
            return Response({'detail': 'Ребёнок не найден.'}, status=status.HTTP_404_NOT_FOUND)

        stats = _build_child_stats(child)
        serializer = ChildStatsSerializer(stats, context={'request': request})
        return Response(serializer.data)


class FamilyStatsView(APIView):
    permission_classes = [IsParent]

    def get(self, request):
        children = ChildProfile.objects.filter(parent=request.user)
        children_stats = [_build_child_stats(c) for c in children]

        total_points = sum(s['total_points'] for s in children_stats)
        total_submissions = sum(s['total_submissions'] for s in children_stats)
        approved_submissions = sum(s['approved_submissions'] for s in children_stats)
        total_achievements = sum(s['achievements_count'] for s in children_stats)

        data = {
            'total_children': children.count(),
            'total_points': total_points,
            'total_submissions': total_submissions,
            'approved_submissions': approved_submissions,
            'total_achievements': total_achievements,
            'children': children_stats,
        }
        serializer = FamilyStatsSerializer(data, context={'request': request})
        return Response(serializer.data)