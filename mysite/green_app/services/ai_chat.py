# coding: utf-8
"""
AI-чат через LangChain + Gemini.
При недоступности API возвращает keyword fallback — не падает с 500.
"""
import logging

from django.conf import settings

logger = logging.getLogger('green_app')

KEYWORD_FALLBACK = {
    'задание': 'Попробуйте выбрать задание, которое соответствует возрасту и интересам вашего ребёнка. Начните с простых заданий категории «Лёгкий» уровень.',
    'балл': 'Баллы начисляются за каждое выполненное и подтверждённое задание. Чем сложнее задание — тем больше баллов!',
    'уровень': 'Уровень повышается автоматически при накоплении баллов. Каждый новый уровень открывает более сложные задания.',
    'достижение': 'Достижения разблокируются при выполнении определённого количества заданий и наборе баллов. Это отличная мотивация!',
    'мотив': 'Хвалите ребёнка за каждое выполненное задание! Маленькие победы создают большую уверенность в себе.',
    'серия': 'Серия дней — это подряд идущие дни, когда ребёнок выполняет хотя бы одно задание. Поддерживайте её!',
}

DEFAULT_FALLBACK = (
    'Я помогаю родителям в вопросах воспитания, развития детей и работы с платформой GreenLearn. '
    'Задайте вопрос о заданиях, баллах, уровнях или мотивации ребёнка.'
)


def build_system_prompt(child=None) -> str:
    base = (
        'Ты — дружелюбный AI-помощник платформы GreenLearn для родителей детей 2–10 лет. '
        'Отвечай на русском языке. Давай советы по:\n'
        '- воспитанию и развитию детей\n'
        '- выбору подходящих заданий для ребёнка\n'
        '- мотивации ребёнка выполнять задания\n'
        '- объяснению системы баллов и уровней\n'
        'Будь позитивным, используй простые слова.'
    )
    if child:
        base += (
            f'\n\nКонтекст ребёнка:\n'
            f'- Имя: {child.name}\n'
            f'- Возраст: {child.age} лет\n'
            f'- Уровень: {child.level}\n'
            f'- Баллы: {child.total_points}\n'
            f'- Серия дней: {child.streak_days}\n'
            'Давай советы с учётом возраста и прогресса этого ребёнка.'
        )
    return base


def _keyword_fallback(user_message: str) -> str:
    lower = user_message.lower()
    for keyword, response in KEYWORD_FALLBACK.items():
        if keyword in lower:
            return response
    return DEFAULT_FALLBACK


def chat_with_ai(user_message: str, history: list, child=None) -> str:
    """
    Отправить сообщение в Gemini через LangChain.
    При любой ошибке — вернуть keyword fallback.
    """
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import SystemMessage, HumanMessage
        from langchain_core.messages import AIMessage as LangAIMessage

        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            logger.warning('chat_with_ai: GEMINI_API_KEY не задан, используется fallback')
            return _keyword_fallback(user_message)

        llm = ChatGoogleGenerativeAI(
            model='gemini-2.0-flash-lite',
            google_api_key=api_key,
            temperature=0.7,
            max_tokens=1024,
        )

        messages = [SystemMessage(content=build_system_prompt(child))]
        for msg in history:
            if msg.role == 'user':
                messages.append(HumanMessage(content=msg.message))
            else:
                messages.append(LangAIMessage(content=msg.message))
        messages.append(HumanMessage(content=user_message))

        response = llm.invoke(messages)

        if isinstance(response.content, str):
            return response.content
        elif isinstance(response.content, list):
            return ''.join(
                block.get('text', '')
                for block in response.content
                if isinstance(block, dict) and block.get('type') == 'text'
            )
        return str(response.content)

    except Exception as exc:
        logger.error('chat_with_ai error: %s', exc)
        return _keyword_fallback(user_message)