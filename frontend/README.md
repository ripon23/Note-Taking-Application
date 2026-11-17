# Secure Notes frontend

A static browser client for the Secure Notes API. It supports regular and administrator sign-in, personal note management, public post creation and lookup, administrator user management, the all-notes view, and interest groups. The bearer token is stored in tab-scoped session storage so valid sessions survive refreshes. The app checks it with the API on reload and removes it on sign-out or rejection by the API.

## Local development

Start the backend at `http://localhost:3000`, then run this command in the frontend directory:

```sh
python3.13 -m http.server 5173 --bind 127.0.0.1
```

Open [localhost:5173](http://localhost:5173). No JavaScript package installation or build is needed.

## Deploy

Set `productionApi` in `config.js` to the deployed API origin with HTTPS and no `/api` suffix. Import this repository into Vercel as a static project using the Other preset. Add the Vercel production origin to the API's `FRONTEND_ORIGIN` setting.
