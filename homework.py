import logging
import os
import time
from datetime import datetime
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import HomeworkError, ResponseStatusNotOK, TokenCheckError

os.environ.clear()
load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    filename=os.path.expanduser('~/.homework_bot.log'),
    filemode='w',
    encoding='utf-8',
    format=('%(asctime)s - %(levelname)s - %(message)s - %(filename)s '
            '- %(name)s - %(lineno)d'),
)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())


def check_tokens():
    """Проверяет доступность необходимых переменных окружения."""
    lost_tokens = []
    for name, value in (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN,),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN,),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID,),
    ):
        if value is None:
            lost_tokens.append(name)
            logger.critical(f'Не найдена переменная окружения: {name}')
        if lost_tokens:
            raise TokenCheckError(
                'Не найдены необходимые переменные окружения: '
                f'{", ".join(lost_tokens)}'
            )


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат, определяемый TELEGRAM_CHAT_ID.

    Принимает на вход экземпляр класса TeleBot и строку с текстом сообщения.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as tg_error:
        logger.error(f'Сообщение в Телеграм не отправлено: {tg_error}.'
                     f'Текст сообщения: {message}')
        return False
    logger.debug(f'В Телеграм отправлено сообщение: {message}')
    return True


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса.

    Принимает на вход временную метку начала периода отслеживания. В ответе API
    ожидает получить JSON. В случае успешного запроса возвращает ответ API,
    приведённый к типам данных Python.
    """
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    params_msg = (f'Эндпоинт: {request_params["url"]} '
                  f'Авторизация: {request_params["headers"]["Authorization"]} '
                  f'Метка времени: {request_params["params"]["from_date"]} ')

    logger.debug(f'Отправляем запрос со следующими параметрами: {params_msg}')
    try:
        response = requests.get(request_params["url"],
                                headers=request_params["headers"],
                                params=request_params["params"])
    except requests.exceptions.RequestException as request_error:
        raise ConnectionError(
            'Ошибка запроса. Запрос с параметрами: '
            f'{params_msg} завершился ошибкой {request_error}'
        )
    if response.status_code != HTTPStatus.OK:
        raise ResponseStatusNotOK('Запрошенный ресурс недоступен.'
                                  f'Код ответа: {response.status_code}'
                                  f'Причина: {response.reason}'
                                  f'Ответ сервера: {response.text}')
    return response.json()


def check_response(response):
    """Проверяет ответ на соответствие документации API."""
    if not isinstance(response, dict):
        raise TypeError('В ответе сервера ожидали dict, а получили '
                        f'{response.__class__.__name__}')
    if 'homeworks' not in response:
        raise TypeError('В ответе сервера не найден ключ "homeworks"')
    if not isinstance(response['homeworks'], list):
        raise TypeError('В ответет сервера под ключом "homeworks" ожидали'
                        'list, а получили '
                        f'{response["homeworks"].__class__.__name__}!')
    return response['homeworks']


def parse_status(homework):
    """Возвращает статус домашней работы.

    Получает на вход один элемент из списка домашних работ. В случае успеха
    возвращает строку, содержащую один из вердиктов словаря HOMEWORK_VERDICTS.
    """
    if 'homework_name' not in homework:
        raise HomeworkError('Ключ "homework_name" не найден в ответе API')
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        raise HomeworkError(f'Полученный статус домашки "{homework_status}" '
                            'не соответствует ни одному из ожидаемых: '
                            f'{"|".join(HOMEWORK_VERDICTS.keys())}')
    return (f'Изменился статус проверки работы "{homework_name}". '
            f'{HOMEWORK_VERDICTS[homework_status]}')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    send_message(bot, (f'{datetime.now().strftime("%d.%m.%y %H:%M")}: '
                       'Начали отслеживать статус домашки.'))
    prev_status = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks == []:
                logger.debug('В ответе сервера нет ни одной домашки.')
                continue
            homework = homeworks[0]
            verdict = parse_status(homework)
            if homework['status'] != prev_status:
                if send_message(bot, verdict):
                    prev_status = homework['status']
                    timestamp = response.get('current_date')
                    continue
            logger.info('Статус домашки не изменился, повторный запрос через '
                        f'{RETRY_PERIOD} с.')
        except Exception as error:
            prev_err_msg = ''
            err_msg = f'Сбой в работе программы: {error}'
            logger.error(err_msg)
            if err_msg != prev_err_msg:
                if send_message(bot, err_msg):
                    prev_err_msg = err_msg
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
