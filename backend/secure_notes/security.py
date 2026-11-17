from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from functools import wraps
from hashlib import scrypt
from hmac import compare_digest
from secrets import token_bytes
from threading import BoundedSemaphore, Lock
from time import monotonic

import jwt
from flask import current_app, g, request

from .validation import ApiError, object_id

ISSUER = 'secure-notes-api'
AUDIENCE = 'secure-notes-web'
MAX_HASHES = BoundedSemaphore(2)
PUBLIC_PROFILE = {key: 1 for key in ('name', 'email', 'role', 'interests', 'createdAt')}


def now():
    return datetime.now(timezone.utc)


def derive(password, salt):
    if not MAX_HASHES.acquire(blocking=False):
        raise ApiError(503, 'Authentication is busy. Try again shortly.')
    try:
        return scrypt(password.encode(), salt=salt, n=2**17, r=8, p=1,
                      maxmem=192 * 1024 * 1024, dklen=64)
    finally:
        MAX_HASHES.release()


def hash_password(password):
    salt = token_bytes(16)
    return f'{salt.hex()}:{derive(password, salt).hex()}'


def verify_password(password, stored=None):
    salt, expected = stored.split(':') if stored else ('00' * 16, '00' * 64)
    return compare_digest(derive(password, bytes.fromhex(salt)), bytes.fromhex(expected))


def create_account(db, attributes):
    user = {'role': 'user', 'interests': [], **attributes, 'tokenVersion': 0, 'createdAt': now()}
    user['passwordHash'] = hash_password(user.pop('password'))
    db.users.insert_one(user)
    return user


def profile(user):
    return {key: user[key] for key in ('_id', *PUBLIC_PROFILE)}


def issue_token(user):
    issued_at = now()
    expires_at = issued_at + timedelta(minutes=current_app.config['JWT_TTL_MINUTES'])
    return jwt.encode({
        'sub': str(user['_id']), 'version': user['tokenVersion'], 'iss': ISSUER,
        'aud': AUDIENCE, 'iat': issued_at, 'exp': expires_at,
    }, current_app.config['JWT_SECRET'], algorithm='HS256')


def authenticated(*, admin=False):
    def decorator(endpoint):
        @wraps(endpoint)
        def protected(*args, **kwargs):
            header = request.headers.get('Authorization', '').split()
            if len(header) != 2 or header[0].lower() != 'bearer':
                raise ApiError(401, 'Sign in with a valid session')
            try:
                claims = jwt.decode(header[1], current_app.config['JWT_SECRET'], algorithms=['HS256'],
                                    issuer=ISSUER, audience=AUDIENCE,
                                    options={'require': ['exp', 'iat', 'sub', 'version']})
                user_id = object_id(claims['sub'])
            except (jwt.InvalidTokenError, ApiError):
                raise ApiError(401, 'Sign in with a valid session') from None
            db = current_app.extensions['notes_db']
            user = db.users.find_one({'_id': user_id}, {**PUBLIC_PROFILE, 'tokenVersion': 1})
            if not user or claims['version'] != user['tokenVersion']:
                raise ApiError(401, 'Sign in with a valid session')
            if admin and user['role'] != 'admin':
                raise ApiError(403, 'Administrator access required')
            g.user = user
            return endpoint(*args, **kwargs)
        return protected
    return decorator


class LoginLimiter:
    """Bounded, per-process fixed-window limiter for login and registration."""

    def __init__(self):
        self.windows = OrderedDict()
        self.lock = Lock()

    def check(self):
        client = request.remote_addr
        timestamp = monotonic()
        with self.lock:
            while self.windows and next(iter(self.windows.values()))[0] <= timestamp:
                self.windows.popitem(last=False)
            expires, count = self.windows.get(client, (timestamp + 900, 0))
            if count >= 25:
                raise ApiError(429, 'Too many sign-in or registration attempts. Try again later.')
            if client not in self.windows and len(self.windows) >= 10000:
                raise ApiError(503, 'Authentication is busy. Try again shortly.')
            self.windows[client] = expires, count + 1
