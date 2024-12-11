class BaseException(Exception):
    """Базовый класс исключений для бота-ассистента."""

    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None


class ResponseStatusNotOK(BaseException):
    """Неожиданный статус ответа сервера."""

    def __str__(self):
        if self.message:
            return self.message
        else:
            return 'Ошибка соединения с сервисом!'


class HomeworkError(BaseException):
    """Ответ сервера не соответствует документации API."""

    def __str__(self):
        if self.message:
            return self.message
        else:
            return 'Ответ сервера не соответствует документации API.'


class TokenCheckError(BaseException):
    """Ошибка окружения."""

    def __str__(self):
        if self.message:
            return self.message
        else:
            return 'Ошибка при проверке окружения!'
