# Secure Notes API

Python 3.13, Flask, PyMongo, MongoDB, PyJWT and scrypt. The initial administrator is created from the command line. Self-registration always creates a regular user.

The original brief requires Mongoose and `schema.index()`. The requested Python implementation uses PyMongo and declares its indexes in [secure_notes/database.py](secure_notes/database.py).

## Setup

```sh
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set the MongoDB URI including its database name and generate `JWT_SECRET` with `openssl rand -hex 32`. Then run:

```sh
python -m secure_notes.create_admin --email admin@example.com
python -m flask --app secure_notes.app run --port 3000
```

For hosted deployment, use `render.yaml` or run the Gunicorn command defined there. Set `FRONTEND_ORIGIN` to the frontend's origin and use `TRUST_PROXY=1` when deployed behind the Render proxy.


## Deploy on Vercel

For the backend project, set **Root Directory** to `backend` when deploying the combined repository and use the **Flask** framework preset. Vercel loads the Flask app from `app.py`. Leave the build and output overrides off.

Set `MONGODB_URI` to a reachable MongoDB connection string that includes its database name, `JWT_SECRET` to a random secret, and `FRONTEND_ORIGIN` to the deployed frontend origin. Verify the deployment at `/api/health`.

## Configuration

Set these optional values in local `.env` or in the hosting environment, then restart the API.

| Variable | Default | Effect |
| --- | --- | --- |
| `PAGINATION_DEFAULT_LIMIT` | 20, capped by the configured maximum | Page size when the request omits `limit`. The frontend uses this setting. |
| `PAGINATION_MAX_LIMIT` | 50 | Largest accepted `limit`, configurable from 1 to 100. |
| `JWT_TTL_MINUTES` | 60 | Lifetime of newly issued JWTs, configurable from 1 to 1,440 minutes. |

## API

All paths start with `/api`. Authenticated routes expect `Authorization: Bearer <token>`. Send bodies as JSON. List routes accept `page` and `limit` and return `items`, `page`, `limit`, and `hasNext`.

| Method and path | Access | Purpose |
| --- | --- | --- |
| GET `/health` | Public | Check database connectivity |
| POST `/auth/register` | Public | Sign up with name, email, password and optional interests |
| POST `/auth/login` | Public | Exchange email and password for a JWT |
| GET `/auth/me` | Signed in | Get the current profile |
| GET, POST `/notes` | Signed in | List own notes or create a note with title and body |
| GET `/notes/:id` | Owner or admin | Read a single note |
| PATCH, DELETE `/notes/:id` | Owner | Update or delete a note |
| POST `/posts` | Signed in | Publish a post with title and body |
| GET `/users/:id/posts` | Public | List a specific author's public posts |
| GET `/admin/notes` | Admin | List all notes |
| GET, POST `/admin/users` | Admin | List users or add an account, optionally with a role |
| GET, PATCH, DELETE `/admin/users/:id` | Admin | Read, update or remove an account |
| GET `/admin/interests` | Admin | List interest groups and their members |

Administrators have full control of their own notes and read access to others' notes. Account deletion invalidates the account's sessions and removes the author from public lookups. Existing note and post documents are retained, and admins can still audit retained notes. Password, role, and email changes also invalidate existing sessions.

## Indexes and aggregation

| Collection | Index | Query |
| --- | --- | --- |
| Users | `email` (unique) | Login and uniqueness on account writes |
| Users | `createdAt DESC, _id DESC` | Admin user list |
| Users | `interests` (multikey) | Filter users with indexed interest values before unwinding |
| Notes | `owner, createdAt DESC, _id DESC` | Paginated personal notes |
| Notes | `createdAt DESC, _id DESC` | Paginated admin notes across owners |
| Posts | `author, createdAt DESC, _id DESC` | Author equality and descending post order within the lookup |

MongoDB's built-in `_id` indexes support note and profile fetches, the per-request session check and the first stage of the posts pipeline. An `_id` tie-breaker keeps each ordered list deterministic when timestamps match.

The interest endpoint makes one `users.aggregate()` call. The initial match uses the multikey index, then the pipeline unwinds interest values, groups members and paginates the resulting groups. The index serves the input match. MongoDB computes the resulting group keys and sorts those derived values. The endpoint returns complete member lists, so one exceptionally large group can reach MongoDB's BSON document size limit.

The public posts endpoint also makes one `users.aggregate()` call. It matches the author by `_id`, then pages the posts inside `$lookup`. Both aggregations fetch one extra result to compute `hasNext` without a separate count query.
