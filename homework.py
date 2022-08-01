import logging
import os
import time
import types
from sys import stdout

import requests
import telegram
from dotenv import load_dotenv

from exceptions import ResponseError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message) -> dict:
    """Отправляет сообщение в Telegram чат.
    Возвращает флаг успеха и объект ошибки в случае провала
    """
    try:
        bot.sendMessage(TELEGRAM_CHAT_ID, message)
        return {'success': True, 'error': None}
    except Exception as error:
        return {'success': False, 'error': error}


def get_api_answer(timestamp) -> dict:
    """Делает запрос к эндпоинту API-сервиса Яндекс Практикума.
    Загружает сведения о заданиях с момента current_timestamp.
    Если код состояния отличается от 200, выбрасывает исключение.
    """
    params = {'from_date': timestamp}
    response = requests.get(ENDPOINT, headers=HEADERS, params=params)

    if not isinstance(response, requests.models.Response):
        """В тестах используется mock объект, который не имеет метода
        raise_for_status(), поэтому его и поле reason (которое участвует в
        работе метода) пришлось добавить вручную, чтобы пройти тесты
        """
        response.raise_for_status = types.MethodType(
            requests.models.Response.raise_for_status, response
        )
        response.reason = None

    response.raise_for_status()
    return response.json()


def check_response(response) -> list:
    """Проверка корректности структуры и формата ответа, полученного от API."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарём')

    homeworks = response.get('homeworks')

    if homeworks is None:
        raise ResponseError('Ошибочный ответ API. Отсутствует список работ')
    if not isinstance(homeworks, list):
        raise TypeError(
            'Ошибочный ответ API. Некорректный формат списка работ'
        )

    return homeworks


def parse_status(homework) -> str:
    """Возвращает информационное сообщение со статусом проверки работы."""
    homework_name = homework['homework_name']
    homework_status = homework['status']

    verdict = HOMEWORK_VERDICTS.get(homework_status)
    if verdict is None:
        raise ResponseError('Недокументированный статус домашней работы')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """Проверка корректной загрузки переменных окружения."""
    return (
        isinstance(PRACTICUM_TOKEN, str) and isinstance(TELEGRAM_TOKEN, str)
        and (isinstance(TELEGRAM_CHAT_ID, str)
             or isinstance(TELEGRAM_CHAT_ID, int))
    )


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Ошибка при загрузке переменных окружения. '
                        'Программа принудительно остановлена')
        exit(-1)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_sent_error = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            homeworks = response.get('homeworks')
            if homeworks:
                msg = parse_status(homeworks[0])
                sent_msg_result = send_message(bot, msg)
                if sent_msg_result['success']:
                    logger.info('Отправлено сообщение для id '
                                f'{TELEGRAM_CHAT_ID}')
                else:
                    logger.error(
                        'Ошибка при отправке сообщения для id '
                        f"{TELEGRAM_CHAT_ID} ({sent_msg_result['error']})"
                    )

            timestamp = response.get('current_date')
        except Exception as error:
            msg = f'Сбой в работе программы: {error}'
            if msg != last_sent_error:
                send_message(bot, msg)
                last_sent_error = msg
            logger.error(msg)
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    c_handler = logging.StreamHandler(stdout)
    f_handler = logging.FileHandler(filename='main.log', mode='a',
                                    encoding='utf-8')

    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - %(message)s'
    )
    c_handler.setFormatter(formatter)
    f_handler.setFormatter(formatter)

    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

    main()
