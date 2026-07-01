import io
import os
from datetime import timedelta
from textwrap import dedent

from flask import Flask, abort, jsonify, send_file, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from dotenv import find_dotenv, load_dotenv
from app.token_store import is_token_revoked, cleanup_blocklist, clear_blocklist

load_dotenv(find_dotenv(usecwd=True))

# Initialize SocketIO globally.
# Use threading mode so the backend runs on Python 3.13 / Windows without eventlet.
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")


def _build_openapi_spec(base_url: str = ""):
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Chess Backend API",
            "version": "1.0.0",
            "description": "REST API for authentication, messaging, notes, stories, uploads, and real-time chat.",
        },
        "servers": [{"url": base_url or "/"}],
        "paths": {
            "/api/auth/register": {
                "post": {
                    "summary": "Register user",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "email", "first_name", "last_name", "password"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "email": {"type": "string"},
                                        "first_name": {"type": "string"},
                                        "last_name": {"type": "string"},
                                        "password": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {"description": "User registered successfully"},
                        "400": {"description": "Validation error"},
                    },
                }
            },
            "/api/auth/login": {
                "post": {
                    "summary": "Login user",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Login successful"},
                        "401": {"description": "Invalid credentials"},
                    },
                }
            },
            "/api/auth/health": {
                "get": {
                    "summary": "Auth health check",
                    "responses": {"200": {"description": "Healthy"}},
                }
            },
            "/api/auth/validate-token": {
                "get": {
                    "summary": "Validate JWT token",
                    "security": [{"bearerAuth": []}],
                    "responses": {"200": {"description": "Token valid"}, "401": {"description": "Unauthorized"}},
                }
            },
            "/api/auth/refresh": {
                "post": {
                    "summary": "Refresh access token",
                    "security": [{"bearerAuth": []}],
                    "responses": {"200": {"description": "Token refreshed"}, "401": {"description": "Unauthorized"}},
                }
            },
            "/health": {
                "get": {
                    "summary": "Service health check",
                    "responses": {"200": {"description": "Healthy"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            }
        },
    }


def _swagger_ui_html(spec_url: str) -> str:
    return dedent(
        f"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Chess Backend API Docs</title>
          <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
          <style>html, body {{ margin: 0; padding: 0; height: 100%; }} #swagger-ui {{ height: 100%; }}</style>
        </head>
        <body>
          <div id="swagger-ui"></div>
          <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
          <script>
            window.ui = SwaggerUIBundle({{
              url: "{spec_url}",
              dom_id: '#swagger-ui',
              deepLinking: true,
              presets: [SwaggerUIBundle.presets.apis],
              layout: "BaseLayout"
            }});
          </script>
        </body>
        </html>
        """
    ).strip()

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-jwt-secret-key-change-in-production')
    app.config['JWT_TOKEN_LOCATION'] = ['headers']
    app.config['JWT_HEADER_NAME'] = 'Authorization'
    app.config['JWT_HEADER_TYPE'] = 'Bearer'
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=90)
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', str(100 * 1024 * 1024)))
    
    # Enable CORS for Flutter frontend (including uploads)
    allowed_origins_raw = os.getenv('ALLOWED_ORIGINS', '*')
    allowed_origins = [
        origin.strip()
        for origin in allowed_origins_raw.split(',')
        if origin.strip()
    ] or '*'
    cors_resources = {
        r"/api/*": {"origins": allowed_origins},
        r"/uploads/*": {"origins": allowed_origins},
        r"/media/*": {"origins": allowed_origins},
        r"/socket.io/*": {"origins": allowed_origins},
    }
    CORS(app, resources=cors_resources)
    
    # Initialize JWT Manager
    jwt = JWTManager(app)

    @jwt.unauthorized_loader
    def unauthorized_response(message):
        return jsonify({'success': False, 'message': message}), 401

    @jwt.invalid_token_loader
    def invalid_token_response(message):
        return jsonify({'success': False, 'message': message}), 401

    @jwt.expired_token_loader
    def expired_token_response(jwt_header, jwt_payload):
        return jsonify({'success': False, 'message': 'Token has expired'}), 401

    @jwt.revoked_token_loader
    def revoked_token_response(jwt_header, jwt_payload):
        return jsonify({'success': False, 'message': 'Token has been revoked'}), 401

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        return is_token_revoked(jwt_payload.get('jti'))
    
    # Initialize Socket.IO with the app
    socketio.init_app(app)

    @app.after_request
    def apply_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Cache-Control'] = 'no-store'
        return response
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.messaging import messaging_bp
    from app.routes.stories import stories_bp
    from app.routes.notes import notes_bp
    from app.routes.friends import friends_bp
    from app.routes.upload import upload_bp
    from app.routes.debug import debug_bp
    from app.routes.tournament import tournament_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(messaging_bp, url_prefix='/api/messages')
    app.register_blueprint(friends_bp, url_prefix='/api/friends')
    app.register_blueprint(stories_bp, url_prefix='/api/stories')
    app.register_blueprint(notes_bp, url_prefix='/api/notes')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(debug_bp, url_prefix='/api/debug')
    app.register_blueprint(tournament_bp, url_prefix='/api/tournaments')
    # Register payments blueprint for eSewa
    from app.routes.payments_flask import payments_bp
    app.register_blueprint(payments_bp, url_prefix='/api/payments')

    # Register Socket.IO handlers (messaging + call signaling)
    from app import websocket as ws_handlers  # noqa: F401

    @app.route('/')
    def home():
        return {
            'service': 'chess-backend',
            'status': 'running',
            'message': 'Chess backend is live',
            'health_check': '/api/ping',
            'docs': '/docs',
        }

    @app.route('/ping')
    def ping():
        return jsonify({'status': 'ok', 'service': 'chess-backend'}), 200

    @app.route('/openapi.json')
    def openapi_json():
        return jsonify(_build_openapi_spec())

    @app.route('/docs')
    @app.route('/swagger')
    def swagger_docs():
        return _swagger_ui_html('/openapi.json')
    
    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        uploads_dir = os.path.join(os.getcwd(), 'uploads')
        return send_from_directory(uploads_dir, filename)

    @app.route('/media/<media_id>')
    def serve_media(media_id):
        from app.storage import get_media_file

        row = get_media_file(media_id)
        if not row:
            abort(404)

        return send_file(
            io.BytesIO(row['data']),
            mimetype=row.get('content_type') or 'application/octet-stream',
            as_attachment=False,
            download_name=row.get('filename') or media_id,
        )
    
    # Start background cleanup task
    from app.cleanup import start_cleanup_thread
    start_cleanup_thread()
    # Optionally clear auth/token state on startup if requested by the environment.
    # Useful when deploying to a fresh environment and you want to avoid reusing
    # previously persisted token blocklists across deployments (e.g. HF Spaces).
    if os.getenv('RESET_AUTH_DATA', '0') == '1' or os.getenv('CLEAR_TOKEN_BLOCKLIST_ON_STARTUP', '0') == '1':
        try:
            clear_blocklist()
            app.logger.info('Auth token blocklist cleared on startup due to env flag.')
        except Exception:
            app.logger.exception('Failed to clear token blocklist on startup')
    # Always attempt to clean up expired entries in the blocklist (if present)
    try:
        cleanup_blocklist()
    except Exception:
        app.logger.exception('Failed to cleanup token blocklist')

    # Warn if JWT secret uses default value (encourage setting env var)
    if os.getenv('JWT_SECRET_KEY') is None:
        app.logger.warning('JWT_SECRET_KEY not explicitly set; using default from config.')

    # Debug endpoint to inspect socket state (development only)
    @app.route('/debug/socket_state')
    def debug_socket_state():
        try:
            # Access active_connections and call_rooms from websocket module
            return {
                'active_connections': getattr(ws_handlers, 'active_connections', {}),
                'call_rooms': getattr(ws_handlers, 'call_rooms', {}),
            }
        except Exception as e:
            return {'error': str(e)}, 500
    
    return app
