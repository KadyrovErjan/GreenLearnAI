# coding: utf-8
"""
AI-проверка фото выполненного задания через Gemini Vision.
При недоступности API → статус PENDING, не падает с 500.
"""
import base64
import json
import logging
import re

from django.conf import settings

logger = logging.getLogger('green_app')


def _read_image_base64(image_field) -> tuple[str, str]:
    """Прочитать ImageField и вернуть (base64_data, media_type)."""
    image_field.open('rb')
    raw = image_field.read()
    image_field.close()
    b64 = base64.b64encode(raw).decode('utf-8')

    name = image_field.name.lower()
    if name.endswith('.png'):
        media_type = 'image/png'
    elif name.endswith('.gif'):
        media_type = 'image/gif'
    elif name.endswith('.webp'):
        media_type = 'image/webp'
    else:
        media_type = 'image/jpeg'

    return b64, media_type


def check_mission_photo(submission) -> dict:
    """
    Отправить фото задания в Gemini Vision.

    Возвращает dict:
        {
            "completed": bool,
            "confidence": float,
            "feedback": str,
            "auto_approved": bool,
        }
    При ошибке возвращает {"completed": False, "confidence": 0.0, "feedback": "", "auto_approved": False}.
    """
    from green_app.services.gamification import award_points, update_streak, unlock_achievements
    from green_app.models import MissionSubmission

    default_result = {'completed': False, 'confidence': 0.0, 'feedback': '', 'auto_approved': False}

    if not submission.photo:
        return default_result

    try:
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            logger.warning('check_mission_photo: GEMINI_API_KEY не задан')
            return default_result

        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-lite')

        child = submission.child
        mission = submission.mission

        prompt = (
            f'Посмотри на фото. Ребёнок ({child.age} лет) выполнял задание:\n'
            f'«{mission.title}» — {mission.description}\n'
            f'Задание выполнено? Ответь строго в JSON без markdown:\n'
            f'{{"completed": true/false, "confidence": 0.0-1.0, "feedback": "комментарий на русском для родителя"}}'
        )

        b64, media_type = _read_image_base64(submission.photo)
        image_part = {'mime_type': media_type, 'data': b64}

        response = model.generate_content([prompt, image_part])
        raw_text = response.text.strip()

        # убрать возможные markdown-блоки
        raw_text = re.sub(r'```json|```', '', raw_text).strip()

        result = json.loads(raw_text)
        completed = bool(result.get('completed', False))
        confidence = float(result.get('confidence', 0.0))
        feedback = str(result.get('feedback', ''))

        auto_approved = completed and confidence >= 0.7

        if auto_approved:
            submission.status = MissionSubmission.Status.APPROVED
            submission.points_awarded = mission.points
            submission.ai_result = raw_text
            submission.ai_feedback = feedback
            submission.ai_confidence = confidence
            submission.save(update_fields=[
                'status', 'points_awarded', 'ai_result',
                'ai_feedback', 'ai_confidence'
            ])
            award_points(child, mission.points)
            update_streak(child)
            unlock_achievements(child)
            logger.info(
                'check_mission_photo: AUTO APPROVED submission=%s child=%s confidence=%.2f',
                submission.id, child.name, confidence
            )
        else:
            submission.ai_result = raw_text
            submission.ai_feedback = feedback
            submission.ai_confidence = confidence
            submission.save(update_fields=['ai_result', 'ai_feedback', 'ai_confidence'])
            logger.info(
                'check_mission_photo: PENDING (manual review) submission=%s confidence=%.2f',
                submission.id, confidence
            )

        return {
            'completed': completed,
            'confidence': confidence,
            'feedback': feedback,
            'auto_approved': auto_approved,
        }

    except Exception as exc:
        logger.error('check_mission_photo error: %s', exc)
        return default_result