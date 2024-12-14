class ResponseStatusNotOK(Exception):
    """Неожиданный статус ответа сервера."""


class HomeworkError(Exception):
    """Ответ сервера не соответствует документации API."""


class TokenCheckError(Exception):
    """Ошибка окружения."""
