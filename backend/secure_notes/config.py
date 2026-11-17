import os


def integer_setting(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise RuntimeError(f'{name} must be an integer') from None
    if not minimum <= value <= maximum:
        raise RuntimeError(f'{name} must be between {minimum} and {maximum}')
    return value


def load_settings():
    max_page_size = integer_setting('PAGINATION_MAX_LIMIT', 50, 1, 100)
    return {
        'PAGINATION_DEFAULT_LIMIT': integer_setting(
            'PAGINATION_DEFAULT_LIMIT', min(20, max_page_size), 1, max_page_size,
        ),
        'PAGINATION_MAX_LIMIT': max_page_size,
        'JWT_TTL_MINUTES': integer_setting('JWT_TTL_MINUTES', 60, 1, 1440),
    }
