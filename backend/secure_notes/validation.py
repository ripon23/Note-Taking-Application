import re

from bson import ObjectId
from flask import current_app, request


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def json_fields(allowed):
    data = request.get_json()
    if not isinstance(data, dict):
        raise ApiError(400, 'Expected a JSON object')
    if data.keys() - set(allowed):
        raise ApiError(400, 'Unexpected field')
    return data


def text(value, label, minimum, maximum, *, trim=True):
    if not isinstance(value, str):
        raise ApiError(400, f'{label} must be text')
    value = value.strip() if trim else value
    try:
        length = len(value.encode('utf-16-le')) // 2
    except UnicodeEncodeError:
        raise ApiError(400, f'{label} contains invalid Unicode') from None
    if not minimum <= length <= maximum:
        raise ApiError(400, f'{label} must contain {minimum} to {maximum} characters')
    return value


def email(value):
    value = text(value, 'Email', 3, 254).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise ApiError(400, 'Enter a valid email address')
    return value


def password(value, minimum=12):
    return text(value, 'Password', minimum, 128, trim=False)


def account(data, *, partial=False):
    result = {}
    for key, validate in [
        ('name', lambda value: text(value, 'Name', 1, 80)),
        ('email', email),
        ('password', password),
    ]:
        if not partial or key in data:
            result[key] = validate(data.get(key))
    if 'interests' in data:
        values = data['interests']
        if not isinstance(values, list) or len(values) > 12:
            raise ApiError(400, 'Provide up to 12 interests')
        result['interests'] = list(dict.fromkeys(
            text(value, 'Interest', 1, 40).lower() for value in values
        ))
    if 'role' in data:
        if data['role'] not in ('user', 'admin'):
            raise ApiError(400, 'Invalid role')
        result['role'] = data['role']
    return require_changes(result)


def content(*, partial=False):
    data = json_fields(('title', 'body'))
    result = {}
    if not partial or 'title' in data:
        result['title'] = text(data.get('title'), 'Title', 1, 120)
    if not partial or 'body' in data:
        result['body'] = text(data.get('body', ''), 'Body', 0, 10000, trim=False)
    return require_changes(result)


def require_changes(data):
    if not data:
        raise ApiError(400, 'No changes supplied')
    return data


def object_id(value):
    if not isinstance(value, str) or not ObjectId.is_valid(value):
        raise ApiError(400, 'Invalid ID')
    return ObjectId(value)


def number(key, default, maximum):
    values = request.args.getlist(key)
    if not values:
        return default
    if (len(values) != 1 or not re.fullmatch(r'[1-9][0-9]{0,4}', values[0])
            or int(values[0]) > maximum):
        raise ApiError(400, f'{key} must be an integer between 1 and {maximum}')
    return int(values[0])


def pagination():
    config = current_app.config
    page = number('page', 1, 10000)
    limit = number('limit', config['PAGINATION_DEFAULT_LIMIT'], config['PAGINATION_MAX_LIMIT'])
    return page, limit, (page - 1) * limit


def page_result(items, page, limit):
    return {'items': items[:limit], 'page': page, 'limit': limit, 'hasNext': len(items) > limit}
