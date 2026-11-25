import logging
import os
import sys
import time

import requests
import vk_api
from dotenv import load_dotenv

load_dotenv()


PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
VK_TOKEN = os.getenv("VK_TOKEN")
VK_USER_ID = os.getenv("VK_USER_ID")

RETRY_PERIOD = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}


HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)
logger.addHandler(handler)


class ApiError(Exception):
    """Собственное исключение для ошибок API."""

    pass


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        "PRACTICUM_TOKEN": PRACTICUM_TOKEN,
        "VK_TOKEN": VK_TOKEN,
        "VK_USER_ID": VK_USER_ID,
    }
    missing_tokens = [name for name, value in tokens.items() if not value]

    if missing_tokens:
        for name in missing_tokens:
            logger.critical(
                f"Отсутствует обязательная переменная окружения: {name}"
            )
        logger.critical("Программа принудительно остановлена.")
        return False
    return True


def send_message(vk, message):
    """Отправляет сообщение в VK."""
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=int(time.time() * 1000)
        )
        logger.debug(f'Бот отправил сообщение "{message}"')
    except Exception as e:
        logger.error(f"Сбой при отправке сообщения в VK: {e}")


def get_api_answer(timestamp):
    """Делает запрос к API Практикума."""
    params = {"from_date": timestamp}

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException as e:
        raise ApiError(f"Ошибка при запросе к API: {e}")

    if response.status_code != 200:
        raise ApiError(
            f"Эндпоинт {ENDPOINT} недоступен. "
            f"Код ответа API: {response.status_code}"
        )

    try:
        return response.json()
    except ValueError:
        raise ApiError("Ответ API не является валидным JSON")


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError("Ответ API должен быть словарём")

    if "homeworks" not in response:
        raise ApiError("В ответе API отсутствует ключ homeworks")

    if "current_date" not in response:
        raise ApiError("В ответе API отсутствует ключ current_date")

    if not isinstance(response["homeworks"], list):
        raise TypeError("Ключ homeworks должен содержать список")

    return response["homeworks"]


def parse_status(homework):
    """Извлекает статус домашней работы и формирует сообщение."""
    if "homework_name" not in homework:
        raise KeyError("В ответе API отсутствует ключ homework_name")

    if "status" not in homework:
        raise KeyError("В ответе API отсутствует ключ status")

    homework_name = homework["homework_name"]
    status = homework["status"]

    if status not in HOMEWORK_VERDICTS:
        raise ApiError(f"Неожиданный статус домашней работы: {status}")

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)

    # Инициализация VK API через библиотеку
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()

    timestamp = int(time.time()) - 2592000  # Месяц назад для теста
    last_error_message = None

    while True:
        response = None
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logger.debug("В ответе API нет новых статусов домашних работ")
            else:
                for homework in homeworks:
                    message = parse_status(homework)
                    send_message(vk, message)
                    last_error_message = None

        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            logger.error(message)

            if message != last_error_message:
                send_message(vk, message)
                last_error_message = message
        finally:
            if response and "current_date" in response:
                timestamp = response["current_date"]

            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    main()
