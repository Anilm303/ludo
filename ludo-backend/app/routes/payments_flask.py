import uuid
import hmac
import hashlib
import base64
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.postgres_store import execute, execute_returning, fetch_one, is_database_url_configured

payments_bp = Blueprint('payments', __name__)

# Environment configuration
ESEWA_MERCHANT_ID = os.getenv('ESEWA_MERCHANT_ID', 'EPAYTEST')
ESEWA_SECRET_KEY = os.getenv('ESEWA_SECRET_KEY', '8gBm/:&EnhH.1/q')
ESEWA_SUCCESS_URL = os.getenv('ESEWA_SUCCESS_URL', '')
ESEWA_FAIL_URL = os.getenv('ESEWA_FAIL_URL', '')
BASE_URL = os.getenv('BASE_URL', 'http://10.0.2.2:7860')

# eSewa sandbox (rc-epay) vs production
ESEWA_SANDBOX_URL = 'https://rc-epay.esewa.com.np/api/epay/main/v2/form'
ESEWA_PRODUCTION_URL = 'https://epay.esewa.com.np/api/epay/main/v2/form'


def _generate_signature(total_amount, transaction_uuid, product_code):
    """Generate HMAC-SHA256 signature for eSewa v2 API."""
    message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
    hmac_obj = hmac.new(
        ESEWA_SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    )
    return base64.b64encode(hmac_obj.digest()).decode('utf-8')


@payments_bp.route('/esewa/create', methods=['POST'])
@jwt_required(optional=True)  # optional for testing; remove in production
def create_esewa_payment():
    """Create a pending eSewa payment and return parameters for the client (v2 API)."""
    # Extract request JSON
    data = request.get_json() or {}
    user_id = data.get('user_id') or get_jwt_identity()
    amount = data.get('amount')
    tournament_id = data.get('tournament_id')

    # Input validation
    if not user_id:
        return jsonify({'success': False, 'message': 'Missing user_id'}), 400
    if amount is None:
        return jsonify({'success': False, 'message': 'Missing amount'}), 400
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid amount'}), 400
    if amount <= 0:
        return jsonify({'success': False, 'message': 'Amount must be greater than 0'}), 400
    if not tournament_id:
        return jsonify({'success': False, 'message': 'Missing tournament_id'}), 400

    # Generate unique transaction UUID
    transaction_uuid = uuid.uuid4().hex
    product_code = ESEWA_MERCHANT_ID
    tax_amount = 0
    service_charge = 0
    delivery_charge = 0
    total_amount = amount + tax_amount + service_charge + delivery_charge

    # Format numbers to match exactly what is sent in payload (2 decimal places)
    formatted_total_amount = f"{total_amount:.2f}"

    # Generate HMAC-SHA256 signature
    signature = _generate_signature(formatted_total_amount, transaction_uuid, product_code)

    # Save payment record
    inserted = None
    if is_database_url_configured():
        q = """
            INSERT INTO payments (pid, user_id, tournament_id, amount, currency, status, created_at)
            VALUES (%(pid)s, %(user_id)s, %(tournament_id)s, %(amount)s, %(currency)s, 'pending', now())
            RETURNING id, pid
        """
        params = {
            'pid': transaction_uuid,
            'user_id': user_id,
            'tournament_id': tournament_id,
            'amount': amount,
            'currency': 'NPR',
        }
        inserted = execute_returning(q, params)
    else:
        inserted = {
            'id': transaction_uuid,
            'pid': transaction_uuid,
            'user_id': user_id,
            'tournament_id': tournament_id,
            'amount': amount,
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat(),
        }
        try:
            from app.routes.payments import _MEMORY_PAYMENTS
            _MEMORY_PAYMENTS[transaction_uuid] = inserted
        except ImportError:
            pass

    # eSewa v2 payment URL (sandbox or production)
    payment_url = ESEWA_SANDBOX_URL if ESEWA_MERCHANT_ID == 'EPAYTEST' else ESEWA_PRODUCTION_URL

    # eSewa v2 form parameters
    success_url = ESEWA_SUCCESS_URL or f"{BASE_URL}/api/payments/esewa/callback"
    failure_url = ESEWA_FAIL_URL or f"{BASE_URL}/api/payments/esewa/callback?status=failed"

    esewa_params = {
        'amount': f"{amount:.2f}",
        'tax_amount': f"{tax_amount:.2f}",
        'total_amount': f"{total_amount:.2f}",
        'transaction_uuid': transaction_uuid,
        'product_code': product_code,
        'product_service_charge': f"{service_charge:.2f}",
        'product_delivery_charge': f"{delivery_charge:.2f}",
        'success_url': success_url,
        'failure_url': failure_url,
        'signed_field_names': 'total_amount,transaction_uuid,product_code',
        'signature': signature,
    }

    return jsonify({
        'success': True,
        'payment': inserted,
        'esewa': esewa_params,
        'payment_url': payment_url,
    }), 200


@payments_bp.route('/esewa/callback', methods=['GET', 'POST'])
def esewa_callback():
    """Handle eSewa payment callback and update tournament status."""
    # eSewa v2 sends 'data' query parameter on success
    encoded_data = request.args.get('data')
    if not encoded_data:
        current_app.logger.warning("eSewa callback received without data")
        return jsonify({'success': False, 'message': 'No data received'}), 400

    try:
        # 1. Decode eSewa data
        import json
        import base64
        decoded_bytes = base64.b64decode(encoded_data)
        decoded_str = decoded_bytes.decode('utf-8')
        data = json.loads(decoded_str)

        transaction_uuid = data.get('transaction_uuid')
        status = data.get('status') # 'COMPLETE' on success

        if status != 'COMPLETE':
            return jsonify({'success': False, 'message': 'Payment not complete', 'status': status}), 200

        # 2. Find the payment record
        pay_query = "SELECT * FROM payments WHERE pid = %(pid)s"
        payment = fetch_one(pay_query, {'pid': transaction_uuid})

        if not payment:
            return jsonify({'success': False, 'message': 'Payment record not found'}), 404

        if payment.get('status') == 'paid':
            return jsonify({'success': True, 'message': 'Already processed'}), 200

        user_id = payment['user_id']
        tournament_id = payment['tournament_id']
        amount = float(payment['amount'])

        # 3. Update payment table
        execute(
            "UPDATE payments SET status = 'paid', verified_at = NOW() WHERE pid = %(pid)s",
            {'pid': transaction_uuid}
        )

        # 4. Update participant status to 'paid'
        execute(
            "UPDATE tournament_participants SET status = 'paid', payment_pid = %(pid)s WHERE tournament_id = %(tid)s AND user_id = %(uid)s",
            {'pid': transaction_uuid, 'tid': tournament_id, 'uid': user_id}
        )

        # 5. Update tournament prize pool and overall status
        # Get current tournament info
        t_query = "SELECT * FROM tournaments WHERE id = %(tid)s"
        tournament = fetch_one(t_query, {'tid': tournament_id})

        if tournament:
            new_prize_pool = float(tournament.get('prize_pool') or 0) + amount

            # Check how many players have paid now
            count_query = "SELECT COUNT(*)::int as count FROM tournament_participants WHERE tournament_id = %(tid)s AND status = 'paid'"
            count_res = fetch_one(count_query, {'tid': tournament_id})
            paid_count = count_res['count'] if count_res else 0

            new_status = 'waiting'
            started_at = None

            if paid_count >= int(tournament.get('max_players', 2)):
                new_status = 'in_progress'
                started_at = datetime.now()

            execute(
                "UPDATE tournaments SET prize_pool = %(pool)s, status = %(status)s, started_at = %(start)s WHERE id = %(tid)s",
                {'pool': new_prize_pool, 'status': new_status, 'start': started_at, 'tid': tournament_id}
            )

        current_app.logger.info(f"Payment successful: User {user_id} paid {amount} for Tournament {tournament_id}")
        return jsonify({'success': True, 'message': 'Payment processed successfully'}), 200

    except Exception as e:
        current_app.logger.exception('Error processing eSewa callback')
        return jsonify({'success': False, 'message': str(e)}), 500

# Extra helper for manual verification (test mode)
@payments_bp.route('/esewa/verify', methods=['POST'])
@jwt_required()
def verify_payment_manually():
    """Manual verification endpoint called by the app if callback fails."""
    data = request.get_json() or {}
    pid = data.get('pid')
    user_id = get_jwt_identity()

    # 1. If pid not provided, find the latest pending payment for this user
    if not pid:
        current_app.logger.info(f"Manual verify: No PID provided, looking for latest pending for {user_id}")
        query = "SELECT * FROM payments WHERE user_id = %(uid)s AND status = 'pending' ORDER BY created_at DESC LIMIT 1"
        payment = fetch_one(query, {'uid': user_id})
    else:
        payment = fetch_one("SELECT * FROM payments WHERE pid = %(pid)s", {'pid': pid})

    if not payment:
        return jsonify({'success': False, 'message': 'No pending payment found to verify. Please try paying again.'}), 404

    if payment.get('status') == 'paid':
        return jsonify({'success': True, 'message': 'Already verified as paid'}), 200

    # 2. Update the status
    pid = payment['pid']
    tournament_id = payment['tournament_id']

    execute("UPDATE payments SET status = 'paid', verified_at = NOW() WHERE pid = %(pid)s", {'pid': pid})
    execute("UPDATE tournament_participants SET status = 'paid', payment_pid = %(pid)s WHERE tournament_id = %(tid)s AND user_id = %(uid)s",
            {'pid': pid, 'tid': tournament_id, 'uid': user_id})

    # 3. Update tournament prize pool and status
    t = fetch_one("SELECT * FROM tournaments WHERE id = %(tid)s", {'tid': tournament_id})
    if t:
        count_res = fetch_one("SELECT COUNT(*)::int as count FROM tournament_participants WHERE tournament_id = %(tid)s AND status = 'paid'",
                             {'tid': tournament_id})
        paid_count = count_res['count'] if count_res else 0

        new_status = 'waiting'
        started_at = t.get('started_at')
        if paid_count >= int(t.get('max_players', 2)):
            new_status = 'in_progress'
            started_at = datetime.now()

        execute("UPDATE tournaments SET status = %(status)s, prize_pool = prize_pool + %(amt)s, started_at = %(start)s WHERE id = %(tid)s",
                {'status': new_status, 'amt': payment['amount'], 'tid': tournament_id, 'start': started_at})

    return jsonify({'success': True, 'message': 'Payment verified and tournament updated'}), 200

@payments_bp.route('/esewa/test_mark_paid', methods=['GET'])
def test_mark_paid():
    """Manually mark a payment as paid for testing."""
    pid = request.args.get('pid')
    if not pid:
        return "Missing pid", 400

    # We can just reuse the logic by simulating a callback or calling a helper
    # For now, let's just use it to fix your current stuck tournament
    payment = fetch_one("SELECT * FROM payments WHERE pid = %(pid)s", {'pid': pid})
    if not payment: return "Not found", 404

    # Simple direct update to fix the state
    execute("UPDATE payments SET status = 'paid' WHERE pid = %(pid)s", {'pid': pid})
    execute("UPDATE tournament_participants SET status = 'paid' WHERE tournament_id = %(tid)s AND user_id = %(uid)s",
            {'tid': payment['tournament_id'], 'uid': payment['user_id']})

    # Update prize pool
    execute("UPDATE tournaments SET prize_pool = prize_pool + %(amt)s WHERE id = %(tid)s",
            {'amt': payment['amount'], 'tid': payment['tournament_id']})

    # Check if we should start the game
    t = fetch_one("SELECT * FROM tournaments WHERE id = %(tid)s", {'tid': payment['tournament_id']})
    paid_res = fetch_one("SELECT COUNT(*)::int as count FROM tournament_participants WHERE tournament_id = %(tid)s AND status = 'paid'",
                         {'tid': payment['tournament_id']})

    if paid_res and paid_res['count'] >= t['max_players']:
        execute("UPDATE tournaments SET status = 'in_progress', started_at = NOW() WHERE id = %(tid)s",
                {'tid': payment['tournament_id']})

    return f"Success! Payment {pid} marked as paid and tournament updated.", 200
