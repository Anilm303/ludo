---
title: Chess Game Backend
emoji: ♟️
colorFrom: purple
colorTo: indigo
sdk: docker
sdk_version: latest
app_file: run.py
pinned: false
---

# Chess Backend API

A Flask-based REST API for the Chess game application, handling user authentication, messaging, notes, stories, and real-time communication.

This repository also contains a legacy FastAPI/Ludo scaffold in a few files, but the active deploy entrypoint for this project is `run.py` with the Flask app in `app/`.

## Features

- User Registration with validation
- User Login with JWT authentication
- Token validation
- Secure password hashing
- CORS enabled for Flutter frontend
- Health check endpoint

## Setup

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configuration

Update environment variables before running in production:

```python
SECRET_KEY=your-production-secret-key
JWT_SECRET_KEY=your-production-jwt-secret-key
ALLOWED_ORIGINS=https://app.yourdomain.com,https://yourdomain.com
MEDIA_STORAGE=s3
MEDIA_PUBLIC_BASE_URL=https://cdn.yourdomain.com
```

### Run the API

```bash
python run.py
```

The API will be available at `http://localhost:7860`

## Hugging Face Spaces deployment

Use the existing Docker setup in this repository. Do not create the FastAPI sample app from the Hugging Face prompt; this backend is already wired for Flask.

1. Create a new Space with SDK `Docker`.
2. Push the contents of `chess_backend/` to the Space repo.
3. Keep the Dockerfile as the entrypoint and let `run.py` start the Flask app.
4. Set secrets in the Space settings:
  - `SECRET_KEY`
  - `JWT_SECRET_KEY`
  - `ALLOWED_ORIGINS`
  - any S3 or Redis variables you actually use
5. The Space should listen on port `7860`.
6. Your Flutter app should use the Space URL with `/api`, for example:

```bash
flutter build web --release --dart-define=API_BASE_URL=https://<your-space>.hf.space/api --dart-define=SOCKET_BASE_URL=https://<your-space>.hf.space
```

If you are uploading files manually in the Hugging Face web UI, upload the contents of this folder to the Space root and keep these files at the repository root:

- `Dockerfile`
- `run.py`
- `requirements.txt`
- `app/`

Then open `Logs` and confirm the app starts on port `7860`.

## Production deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for Render and custom-domain setup.

## API Endpoints

### 1. Register User
**POST** `/api/auth/register`

Request:
```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "password": "securepassword123"
}
```

Response (Success - 201):
```json
{
  "success": true,
  "message": "User registered successfully",
  "access_token": "eyJhbGc...",
  "user": {
    "username": "john_doe",
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "created_at": "2024-05-03T10:30:00"
  }
}
```

### 2. Login User
**POST** `/api/auth/login`

Request:
```json
{
  "username": "john_doe",
  "password": "securepassword123"
}
```

Response (Success - 200):
```json
{
  "success": true,
  "message": "Login successful",
  "access_token": "eyJhbGc...",
  "user": {
    "username": "john_doe",
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "created_at": "2024-05-03T10:30:00"
  }
}
```

### 3. Validate Token
**GET** `/api/auth/validate-token`

Headers:
```
Authorization: Bearer <access_token>
```

Response (Success - 200):
```json
{
  "success": true,
  "user": {
    "username": "john_doe",
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "created_at": "2024-05-03T10:30:00"
  }
}
```

### 4. Health Check
**GET** `/api/auth/health`

Response:
```json
{
  "status": "healthy",
  "service": "chess-auth-api"
}
```

## Error Responses

All errors follow this format:

```json
{
  "success": false,
  "message": "Error description"
}
```

## Data Persistence

The backend uses PostgreSQL when `DATABASE_URL` is set, and local mode only when it is not. For Hugging Face deployment, use a managed PostgreSQL database instead of a local PC database.

See [DATABASE_SETUP.md](DATABASE_SETUP.md) for the setup and migration steps.

## Security Notes

- Change SECRET_KEY and JWT_SECRET_KEY for production
- Always use HTTPS in production
- Consider implementing rate limiting
- Add refresh token mechanism for long-running sessions
- Implement email verification for registration
