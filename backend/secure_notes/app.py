import os
from datetime import datetime

from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, g, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import load_settings
from .database import NEWEST, connect, interest_pipeline, posts_pipeline
from .security import (
    PUBLIC_PROFILE, LoginLimiter, authenticated, create_account, hash_password, issue_token,
    now, profile, verify_password,
)
from .validation import (
    ApiError, account, content, email, json_fields, object_id, page_result, pagination, password,
)

ACCOUNT_FIELDS = ('name', 'email', 'password', 'interests')
DEFAULT_ORIGINS = 'http://localhost:5173,http://127.0.0.1:5173'


class MongoJSON(DefaultJSONProvider):
    @staticmethod
    def default(value):
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return DefaultJSONProvider.default(value)


def create_app():
    load_dotenv()
    secret = os.environ.get('JWT_SECRET', '')
    if len(secret.encode()) < 32 or secret.startswith('replace-with-'):
        raise RuntimeError('Set JWT_SECRET to a strong random secret')

    app = Flask(__name__)
    app.json = MongoJSON(app)
    app.config.update(load_settings())
    app.config.update(MAX_CONTENT_LENGTH=80 * 1024, JWT_SECRET=secret)
    proxies = int(os.getenv('TRUST_PROXY', '0'))
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies)
    origins = [item.strip() for item in os.getenv('FRONTEND_ORIGIN', DEFAULT_ORIGINS).split(',')]
    if '*' in origins:
        raise RuntimeError('Set FRONTEND_ORIGIN to explicit frontend URLs')
    CORS(app, resources={r'/api/.*': {'origins': origins}},
         allow_headers=['Authorization', 'Content-Type'])
    db = connect(os.environ['MONGODB_URI'])
    app.extensions['notes_db'] = db
    login_limiter = LoginLimiter()

    @app.after_request
    def add_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.errorhandler(ApiError)
    def bad_input(error):
        return {'error': str(error)}, error.status

    @app.errorhandler(DuplicateKeyError)
    def duplicate(_error):
        return {'error': 'Email already in use'}, 409

    @app.errorhandler(HTTPException)
    def http_error(error):
        return {'error': error.name}, error.code

    @app.errorhandler(PyMongoError)
    def database_error(error):
        app.logger.error('Database request failed (%s)', type(error).__name__)
        return {'error': 'Database request failed'}, 503

    def list_page(collection, query, projection=None):
        page, limit, skip = pagination()
        items = list(collection.find(query, projection).sort(NEWEST).skip(skip).limit(limit + 1))
        return page_result(items, page, limit)

    def found(document, label):
        if document is None:
            raise ApiError(404, f'{label} not found')
        return document

    @app.get('/api/health')
    def health():
        db.command('ping')
        return {'status': 'ok'}

    @app.post('/api/auth/register')
    def register():
        login_limiter.check()
        user = create_account(db, account(json_fields(ACCOUNT_FIELDS)))
        return {'user': profile(user), 'token': issue_token(user)}, 201

    @app.post('/api/auth/login')
    def login():
        login_limiter.check()
        values = json_fields(('email', 'password'))
        address = email(values.get('email'))
        candidate = password(values.get('password'), 1)
        user = db.users.find_one({'email': address})
        valid = verify_password(candidate, user['passwordHash'] if user else None)
        if not user or not valid:
            raise ApiError(401, 'Invalid email or password')
        return {'user': profile(user), 'token': issue_token(user)}

    @app.get('/api/auth/me')
    @authenticated()
    def me():
        return profile(g.user)

    @app.get('/api/users/<user_id>/posts')
    def public_posts(user_id):
        page, limit, skip = pagination()
        with db.users.aggregate(posts_pipeline(object_id(user_id), skip, limit)) as cursor:
            user = found(next(cursor, None), 'User')
        return {'user': {'_id': user['_id'], 'name': user['name']},
                **page_result(user['posts'], page, limit)}

    @app.post('/api/posts')
    @authenticated()
    def create_post():
        post = {**content(), 'author': g.user['_id'], 'createdAt': now()}
        db.posts.insert_one(post)
        return post, 201

    @app.get('/api/notes')
    @authenticated()
    def notes():
        return list_page(db.notes, {'owner': g.user['_id']})

    @app.post('/api/notes')
    @authenticated()
    def create_note():
        note = {**content(), 'owner': g.user['_id'], 'createdAt': now(), 'updatedAt': now()}
        db.notes.insert_one(note)
        return note, 201

    @app.route('/api/notes/<note_id>', methods=['GET', 'PATCH', 'DELETE'])
    @authenticated()
    def single_note(note_id):
        query = {'_id': object_id(note_id), 'owner': g.user['_id']}
        if request.method in ('GET', 'HEAD'):
            if g.user['role'] == 'admin':
                del query['owner']
            return found(db.notes.find_one(query), 'Note')
        if request.method == 'PATCH':
            changes = {**content(partial=True), 'updatedAt': now()}
            note = db.notes.find_one_and_update(query, {'$set': changes}, return_document=ReturnDocument.AFTER)
            return found(note, 'Note')
        if not db.notes.delete_one(query).deleted_count:
            raise ApiError(404, 'Note not found')
        return '', 204

    @app.get('/api/admin/notes')
    @authenticated(admin=True)
    def all_notes():
        return list_page(db.notes, {})

    @app.get('/api/admin/interests')
    @authenticated(admin=True)
    def interests():
        page, limit, skip = pagination()
        with db.users.aggregate(interest_pipeline(skip, limit), hint='interests_1') as cursor:
            return page_result(list(cursor), page, limit)

    @app.route('/api/admin/users', methods=['GET', 'POST'])
    @authenticated(admin=True)
    def users():
        if request.method in ('GET', 'HEAD'):
            return list_page(db.users, {}, PUBLIC_PROFILE)
        user = create_account(db, account(json_fields((*ACCOUNT_FIELDS, 'role'))))
        return profile(user), 201

    @app.route('/api/admin/users/<user_id>', methods=['GET', 'PATCH', 'DELETE'])
    @authenticated(admin=True)
    def single_user(user_id):
        user_id = object_id(user_id)
        query = {'_id': user_id}
        if request.method in ('GET', 'HEAD'):
            return found(db.users.find_one(query, PUBLIC_PROFILE), 'User')
        own_account = user_id == g.user['_id']
        if request.method == 'DELETE':
            if own_account:
                raise ApiError(400, 'You cannot delete your own account')
            if not db.users.delete_one(query).deleted_count:
                raise ApiError(404, 'User not found')
            return '', 204

        changes = account(json_fields((*ACCOUNT_FIELDS, 'role')), partial=True)
        if own_account and changes.get('role') == 'user':
            raise ApiError(400, 'You cannot remove your own admin role')
        if 'password' in changes:
            changes['passwordHash'] = hash_password(changes.pop('password'))
        update = {'$set': changes}
        if changes.keys() & {'passwordHash', 'role', 'email'}:
            update['$inc'] = {'tokenVersion': 1}
        user = db.users.find_one_and_update(
            query, update, projection=PUBLIC_PROFILE, return_document=ReturnDocument.AFTER,
        )
        return found(user, 'User')

    return app
