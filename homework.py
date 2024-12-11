import json
import logging
import os
import time
from datetime import datetime, timedelta
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import HomeworkError, ResponseStatusNotOK, TokenCheckError


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
    filename='homework_bot.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s - %(name)s'
)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())


def check_tokens():
    """Проверяет доступность необходимых переменных окружения."""
    token_switch = True
    lost_tokens = []
    for token in (PRACTICUM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN,):
        if token is None:
            token_switch = False
            logger.critical(f'Не найдена переменная окружения: {token}')
            lost_tokens.append(token)
        if not token_switch:
            raise TokenCheckError(
                'Не найдены необходимые переменные окружения: '
                f'{", ".join(lost_tokens)}'
            )
    return token_switch


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат, определяемый TELEGRAM_CHAT_ID.

    Принимает на вход экземпляр класса TeleBot и строку с текстом сообщения.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'В Телеграм отправлено сообщение: {message}')
    except Exception as tg_error:
        logger.error(f'Сообщение в Телеграм не отправлено: {tg_error}.'
                     f'Текст сообщения: {message}')


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса.

    Принимает на вход временную метку начала периода отслеживания. В ответе API
    ожидает получить JSON. В случае успешного запроса возвращает ответ API,
    приведённый к типам данных Python.
    """
    try:
        response = requests.get(ENDPOINT,
                                headers=HEADERS,
                                params={'from_date': timestamp})
        if response.status_code != HTTPStatus.OK:
            # response.raise_for_status()
            err_msg = ('Запрошенный ресурс недоступен. Ответ сервера: '
                       f'{response.status_code}')
            logger.error(err_msg)
            raise ResponseStatusNotOK(err_msg)
        return response.json()
    except requests.exceptions.RequestException as request_error:
        err_msg = f'Ошибка запроса: {request_error}'
        logger.error(err_msg)
        raise requests.exceptions.RequestError(err_msg)
    except json.JSONDecodeError as error:
        err_msg = f'Ошибка обработки JSON: {error}'
        logger.error(err_msg)
        raise json.JSONDecodeError(err_msg)


def check_response(response):
    """Проверяет ответ на соответствие документации API."""
    if not isinstance(response, dict):
        err_msg = ('В ответе сервера ожидали dict, а получили '
                   f'{response.__class__.__name__}')
        logger.error(err_msg)
        raise TypeError(err_msg)
    if 'homeworks' not in response:
        err_msg = ('В ответе сервера не найден ключ "homeworks"')
        logger.error(err_msg)
        raise TypeError(err_msg)
    if not isinstance(response['homeworks'], list):
        raise TypeError('В ответет сервера под ключом "homeworks" ожидали'
                        'list, а получили '
                        f'{response["homeworks"].__class__.__name__}!')
    return True


def parse_status(homework):
    """Возвращает статус домашней работы.

    Получает на вход один элемент из списка домашних работ. В случае успеха
    возвращает строку, содержащую один из вердиктов словаря HOMEWORK_VERDICTS.
    """
    if 'homework_name' not in homework:
        err_msg = ('Ожидаемый ключ "homework_name" не найден в ответе API')
        logger.error(err_msg)
        raise HomeworkError(err_msg)
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        err_msg = (
            f'Полученный статус домашки "{homework_status}" не соответствует '
            f'ни одному из ожидаемых: {"|".join(HOMEWORK_VERDICTS.keys())}'
        )
        logger.error(err_msg)
        raise HomeworkError(err_msg)
    return (f'Изменился статус проверки работы "{homework_name}". '
            f'{HOMEWORK_VERDICTS[homework_status]}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        raise ValueError

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int((datetime.now() - timedelta(weeks=2)).timestamp())
    send_message(bot, (f'{datetime.now().strftime("%d.%m.%y %H:%M")}: '
                       'Начали отслеживать статус домашки.'))
    prev_status = None
    while True:
        try:
            response = get_api_answer(timestamp)
            if check_response(response) and len(response['homeworks']) > 0:
                homework = response['homeworks'][0]
                if homework['status'] != prev_status:
                    send_message(bot, parse_status(homework))
                    prev_status = homework['status']
                    time.sleep(RETRY_PERIOD)
                    continue
                logger.info(
                    f'Статус домашки не изменился, повторный запрос через '
                    f'{RETRY_PERIOD} с.'
                )
            time.sleep(RETRY_PERIOD)
        except Exception as error:
            err_msg = f'Сбой в работе программы: {error}'
            send_message(bot, err_msg)
            logger.critical(err_msg)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
