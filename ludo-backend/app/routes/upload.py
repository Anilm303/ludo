from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
from pathlib import Path
import hashlib
from datetime import datetime

upload_bp = Blueprint('upload', __name__)

UPLOAD_DIR = os.path.join(os.getcwd(), 'uploads', 'chunks')
CHUNK_SIZE = 1024 * 1024  # 1MB chunks
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB max
UPLOAD_SESSIONS = {}  # {session_id: {filename, file_size, md5_hash, chunks, session_dir, username}}


def _calculate_md5(filepath):
    md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            md5.update(chunk)
    return md5.hexdigest()


@upload_bp.route('/start', methods=['POST'])
@jwt_required()
def start_upload():
    data = request.get_json(silent=True) or {}
    filename = data.get('filename')
    file_size = int(data.get('file_size', 0))
    file_hash = data.get('md5_hash')
    username = get_jwt_identity()

    if not filename or file_size <= 0 or file_size > MAX_FILE_SIZE:
        return jsonify({'success': False, 'message': 'Invalid file metadata'}), 400

    session_id = f"{username}_{filename}_{file_hash or int(datetime.utcnow().timestamp())}"
    session_dir = Path(UPLOAD_DIR) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    if session_id in UPLOAD_SESSIONS:
        session = UPLOAD_SESSIONS[session_id]
        return jsonify({
            'success': True,
            'session_id': session_id,
            'chunks_received': len(session['chunks']),
            'status': 'resuming',
        }), 200

    UPLOAD_SESSIONS[session_id] = {
        'filename': filename,
        'file_size': file_size,
        'md5_hash': file_hash,
        'chunks': {},
        'session_dir': str(session_dir),
        'created_at': datetime.utcnow().isoformat(),
        'username': username,
    }

    total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    return jsonify({'success': True, 'session_id': session_id, 'chunk_size': CHUNK_SIZE, 'total_chunks': total_chunks}), 200


@upload_bp.route('/chunk', methods=['POST'])
@jwt_required()
def upload_chunk():
    session_id = request.form.get('session_id')
    try:
        chunk_num = int(request.form.get('chunk_num', -1))
    except Exception:
        chunk_num = -1

    if not session_id or chunk_num < 0:
        return jsonify({'success': False, 'message': 'Invalid session or chunk number'}), 400

    session = UPLOAD_SESSIONS.get(session_id)
    if not session:
        return jsonify({'success': False, 'message': 'Session not found'}), 404

    # Idempotent: skip if chunk already received
    if chunk_num in session['chunks']:
        return jsonify({'success': True, 'message': 'Chunk already received', 'chunk_num': chunk_num}), 200

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400

    uploaded = request.files['file']
    if not uploaded:
        return jsonify({'success': False, 'message': 'Empty file part'}), 400

    try:
        chunk_path = Path(session['session_dir']) / f'chunk_{chunk_num:06d}'
        uploaded.save(str(chunk_path))
        session['chunks'][chunk_num] = True
        total_chunks = (session['file_size'] + CHUNK_SIZE - 1) // CHUNK_SIZE
        progress = len(session['chunks']) / total_chunks * 100
        return jsonify({'success': True, 'chunk_num': chunk_num, 'chunks_received': len(session['chunks']), 'progress': progress, 'total_chunks': total_chunks}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@upload_bp.route('/status', methods=['GET'])
@jwt_required()
def upload_status():
    session_id = request.args.get('session_id')
    if not session_id or session_id not in UPLOAD_SESSIONS:
        return jsonify({'success': False, 'message': 'Session not found'}), 404
    session = UPLOAD_SESSIONS[session_id]
    total_chunks = (session['file_size'] + CHUNK_SIZE - 1) // CHUNK_SIZE
    return jsonify({'success': True, 'session_id': session_id, 'chunks_received': len(session['chunks']), 'total_chunks': total_chunks, 'progress': len(session['chunks']) / total_chunks * 100}), 200


@upload_bp.route('/complete', methods=['POST'])
@jwt_required()
def complete_upload():
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    md5_hash = data.get('md5_hash')

    if not session_id or session_id not in UPLOAD_SESSIONS:
        return jsonify({'success': False, 'message': 'Session not found'}), 404

    session = UPLOAD_SESSIONS[session_id]
    total_chunks = (session['file_size'] + CHUNK_SIZE - 1) // CHUNK_SIZE
    if len(session['chunks']) != total_chunks:
        return jsonify({'success': False, 'message': f'Missing chunks: {len(session["chunks"])}/{total_chunks}'}), 400

    try:
        session_dir = Path(session['session_dir'])
        final_dir = Path(os.path.join(os.getcwd(), 'uploads', 'files'))
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / f"{session_id}_{session['filename']}"
        with open(final_path, 'wb') as final_file:
            for i in range(total_chunks):
                chunk_path = session_dir / f'chunk_{i:06d}'
                if not chunk_path.exists():
                    raise FileNotFoundError(f'Chunk {i} missing')
                with open(chunk_path, 'rb') as cf:
                    final_file.write(cf.read())

        calculated = _calculate_md5(str(final_path))
        if md5_hash and calculated != md5_hash:
            try:
                final_path.unlink()
            except Exception:
                pass
            return jsonify({'success': False, 'message': 'MD5 mismatch'}), 400

        # cleanup chunk folder
        try:
            import shutil
            shutil.rmtree(session_dir)
        except Exception:
            pass

        del UPLOAD_SESSIONS[session_id]
        return jsonify({'success': True, 'file_id': str(final_path.name), 'filename': session['filename'], 'size': session['file_size']}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
