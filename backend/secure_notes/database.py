from pymongo import DESCENDING, MongoClient

NEWEST = [('createdAt', DESCENDING), ('_id', DESCENDING)]


def connect(uri):
    client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
    try:
        db = client.get_default_database()
        db.command('ping')
        db.users.create_index('email', unique=True)
        db.users.create_index(NEWEST)
        db.users.create_index('interests')
        db.notes.create_index([('owner', 1), *NEWEST])
        db.notes.create_index(NEWEST)
        db.posts.create_index([('author', 1), *NEWEST])
        return db
    except Exception:
        client.close()
        raise


def interest_pipeline(skip, limit):
    return [
        {'$match': {'interests': {'$gte': ''}}},
        {'$project': {'name': 1, 'interests': 1}},
        {'$unwind': '$interests'},
        {'$group': {
            '_id': '$interests',
            'count': {'$sum': 1},
            'users': {'$push': {'_id': '$_id', 'name': '$name'}},
        }},
        {'$sort': {'_id': 1}},
        {'$skip': skip},
        {'$limit': limit + 1},
    ]


def posts_pipeline(user_id, skip, limit):
    return [
        {'$match': {'_id': user_id}},
        {'$lookup': {
            'from': 'posts',
            'localField': '_id',
            'foreignField': 'author',
            'pipeline': [
                {'$sort': dict(NEWEST)},
                {'$skip': skip},
                {'$limit': limit + 1},
            ],
            'as': 'posts',
        }},
        {'$project': {'name': 1, 'posts': 1}},
    ]
