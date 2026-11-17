# Secure Notes · Interview setup

The workspace contains two independently publishable projects.

- [Backend](backend/README.md) · Python 3.13, Flask, MongoDB, PyMongo, JWT and scrypt
- [Frontend](frontend/README.md) · HTML, CSS and browser JavaScript

The interview brief specifies Mongoose and `schema.index()`. This version uses Python by request and defines the same query-driven indexes through PyMongo. Confirm with the hiring team that this substitution is acceptable before submitting.

## Run locally on macOS

Python 3.13 and Docker Desktop are already installed on the development Mac. Start Docker Desktop and wait for `docker info` to report a server. Start MongoDB in a local-only container. The first run downloads the MongoDB image.

```sh
docker run -d --name secure-notes-mongo \
  -p 127.0.0.1:27017:27017 \
  -v secure-notes-mongo-data:/data/db mongo:8.0
```

On later days, use `docker start secure-notes-mongo`. An Atlas connection string with a database name also works in `backend/.env` if you prefer a hosted database.

In one terminal, from the workspace root:

```sh
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

This workspace already has an ignored `backend/.env` with a local JWT secret. For a fresh checkout copy `.env.example` to `.env` and set `JWT_SECRET` to the output of `openssl rand -hex 32`.

```sh
python -m secure_notes.create_admin --email admin@example.com
python -m flask --app secure_notes.app run --port 3000
```

In a second terminal, from the workspace root:

```sh
cd frontend
python3.13 -m http.server 5173 --bind 127.0.0.1
```

Open [the local frontend](http://localhost:5173) and check [API health](http://localhost:3000/api/health). Register a regular user with interests, create a note and publish a post. Sign in as the administrator to show the all-notes, users and interests views. Copy a user's ID from the Users view or Public posts screen to try the public posts lookup.

## Publish and deploy

1. Push the contents of each project directory to its own GitHub repository. Ensure the hiring team can access both repositories.
2. Create a MongoDB Atlas cluster and a database user with read/write access to a dedicated `secure_notes` database. Include that database name in the URI and allow the Render service's outbound IP ranges in the Atlas project. [Atlas access setup](https://www.mongodb.com/docs/atlas/security/quick-start/)
3. Create a free Render web service from the backend repository using its `render.yaml` Blueprint. Supply `MONGODB_URI` and an initial `FRONTEND_ORIGIN` value. Render generates `JWT_SECRET`. Verify that `/api/health` returns `{"status":"ok"}`. [Render Flask deployment](https://render.com/docs/deploy-flask)
4. Set `productionApi` in the frontend's `config.js` to the Render service's HTTPS origin with no `/api` suffix. Push the frontend and import it in Vercel with the Other framework preset and default static settings. [Vercel static builds](https://vercel.com/docs/builds)
5. Update `FRONTEND_ORIGIN` in Render to the production Vercel origin. For an admin demo, use the backend admin command with the Atlas connection from a machine allowed by Atlas.
6. Verify sign-in, a note write, and both aggregation views at the deployed URLs. Render's free API can take time to wake after inactivity. [Render free tier](https://render.com/docs/free)

Record the frontend GitHub URL, backend GitHub URL, live Vercel URL, and live Render API URL for the submission.
