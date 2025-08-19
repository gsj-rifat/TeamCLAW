import os
import sys
import hmac
import hashlib
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class SlackBotServer:
    def __init__(self):
        self.app = Flask(__name__)
        self.setup_environment()
        self.setup_routes()

    def setup_environment(self):
        """Load and validate required environment variables"""
        required_vars = [
            'SLACK_SIGNING_SECRET',
            'SLACK_BOT_TOKEN',
            'SLACK_CHANNEL_ID',
            'GROQ_API_KEY'
        ]

        missing_vars = []
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            else:
                setattr(self, var.lower(), value)
                logger.info(f"✓ {var} loaded successfully")

        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            sys.exit(1)

        logger.info("All environment variables loaded successfully")

    def verify_slack_signature(self, request_data, timestamp, signature):
        """Verify that the request is from Slack using the signing secret"""
        if not timestamp or not signature:
            logger.warning("Missing timestamp or signature in request headers")
            return False

        try:
            # Create the signature basestring
            sig_basestring = f"v0:{timestamp}:{request_data}"

            # Create the expected signature
            expected_signature = 'v0=' + hmac.new(
                self.slack_signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256
            ).hexdigest()

            # Compare signatures
            is_valid = hmac.compare_digest(expected_signature, signature)

            if not is_valid:
                logger.warning("Invalid signature received")

            return is_valid

        except Exception as e:
            logger.error(f"Error verifying signature: {str(e)}")
            return False

    def setup_routes(self):
        """Setup Flask routes for Slack webhook endpoints"""

        @self.app.route('/', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'service': 'slack-bot-webhook-server',
                'timestamp': datetime.utcnow().isoformat()
            })

        @self.app.route('/slack/events', methods=['POST'])
        def slack_events():
            """Handle Slack event subscriptions"""
            try:
                # Get request data
                request_data = request.get_data(as_text=True)

                # Parse JSON
                try:
                    data = json.loads(request_data) if request_data else {}
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in request: {str(e)}")
                    return jsonify({'error': 'Invalid JSON'}), 400

                # Handle URL verification challenge
                if 'challenge' in data:
                    challenge = data['challenge']
                    logger.info(f"Responding to URL verification challenge: {challenge}")
                    return jsonify({'challenge': challenge})

                # Verify request signature for security
                timestamp = request.headers.get('X-Slack-Request-Timestamp')
                signature = request.headers.get('X-Slack-Signature')

                if not self.verify_slack_signature(request_data, timestamp, signature):
                    logger.warning("Signature verification failed for events endpoint")
                    return jsonify({'error': 'Invalid signature'}), 403

                # Process Slack events
                if 'event' in data:
                    event = data['event']
                    event_type = event.get('type', 'unknown')

                    logger.info(f"Received Slack event: {event_type}")

                    # Handle different event types
                    response = self.handle_slack_event(event, data)

                    return jsonify(response)

                logger.info("Received Slack request without event data")
                return jsonify({'status': 'ok'})

            except Exception as e:
                logger.error(f"Error processing Slack event: {str(e)}")
                return jsonify({'error': 'Internal server error'}), 500

        @self.app.route('/slack/interactive', methods=['POST'])
        def slack_interactive():
            """Handle Slack interactive components (buttons, modals, etc.)"""
            try:
                # Get request data
                request_data = request.get_data(as_text=True)

                # Verify request signature
                timestamp = request.headers.get('X-Slack-Request-Timestamp')
                signature = request.headers.get('X-Slack-Signature')

                if not self.verify_slack_signature(request_data, timestamp, signature):
                    logger.warning("Signature verification failed for interactive endpoint")
                    return jsonify({'error': 'Invalid signature'}), 403

                # Parse form data (interactive payloads come as form data)
                payload = request.form.get('payload')
                if not payload:
                    logger.error("No payload found in interactive request")
                    return jsonify({'error': 'No payload'}), 400

                try:
                    data = json.loads(payload)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in interactive payload: {str(e)}")
                    return jsonify({'error': 'Invalid JSON payload'}), 400

                # Process interactive component
                interaction_type = data.get('type', 'unknown')
                logger.info(f"Received Slack interactive component: {interaction_type}")

                response = self.handle_slack_interaction(data)

                return jsonify(response)

            except Exception as e:
                logger.error(f"Error processing Slack interaction: {str(e)}")
                return jsonify({'error': 'Internal server error'}), 500

        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({'error': 'Endpoint not found'}), 404

        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({'error': 'Internal server error'}), 500

    def handle_slack_event(self, event, full_data):
        """Handle different types of Slack events"""
        event_type = event.get('type')

        try:
            if event_type == 'message':
                return self.handle_message_event(event, full_data)
            elif event_type == 'app_mention':
                return self.handle_mention_event(event, full_data)
            elif event_type == 'team_join':
                return self.handle_team_join_event(event, full_data)
            else:
                logger.info(f"Unhandled event type: {event_type}")
                return {'status': 'ok'}

        except Exception as e:
            logger.error(f"Error handling {event_type} event: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    def handle_message_event(self, event, full_data):
        """Handle message events"""
        text = event.get('text', '')
        user = event.get('user', 'unknown')
        channel = event.get('channel', 'unknown')

        logger.info(f"Message from {user} in {channel}: {text[:100]}...")

        # Add your message processing logic here
        # For example, you could:
        # - Analyze the message with GROQ API
        # - Send a response back to Slack
        # - Store the message in a database

        return {'status': 'processed'}

    def handle_mention_event(self, event, full_data):
        """Handle app mention events"""
        text = event.get('text', '')
        user = event.get('user', 'unknown')
        channel = event.get('channel', 'unknown')

        logger.info(f"Bot mentioned by {user} in {channel}: {text}")

        # Add your mention handling logic here
        # For example:
        # - Process the mention with your AI model
        # - Send a response back to the channel

        return {'status': 'mention_processed'}

    def handle_team_join_event(self, event, full_data):
        """Handle team join events"""
        user = event.get('user', {})
        user_id = user.get('id', 'unknown')
        user_name = user.get('name', 'unknown')

        logger.info(f"New team member joined: {user_name} ({user_id})")

        # Add welcome message logic here

        return {'status': 'welcome_sent'}

    def handle_slack_interaction(self, data):
        """Handle Slack interactive components"""
        interaction_type = data.get('type')

        try:
            if interaction_type == 'block_actions':
                return self.handle_block_actions(data)
            elif interaction_type == 'view_submission':
                return self.handle_view_submission(data)
            elif interaction_type == 'shortcut':
                return self.handle_shortcut(data)
            else:
                logger.info(f"Unhandled interaction type: {interaction_type}")
                return {'status': 'ok'}

        except Exception as e:
            logger.error(f"Error handling {interaction_type} interaction: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    def handle_block_actions(self, data):
        """Handle button clicks and other block actions"""
        actions = data.get('actions', [])
        user = data.get('user', {}).get('id', 'unknown')

        for action in actions:
            action_id = action.get('action_id')
            value = action.get('value')
            logger.info(f"Block action {action_id} triggered by {user} with value: {value}")

            # Add your button handling logic here

        return {'status': 'action_handled'}

    def handle_view_submission(self, data):
        """Handle modal form submissions"""
        user = data.get('user', {}).get('id', 'unknown')
        view = data.get('view', {})

        logger.info(f"Modal submitted by {user}")

        # Add your modal submission handling logic here

        return {'status': 'submission_processed'}

    def handle_shortcut(self, data):
        """Handle shortcuts"""
        user = data.get('user', {}).get('id', 'unknown')
        callback_id = data.get('callback_id', 'unknown')

        logger.info(f"Shortcut {callback_id} triggered by {user}")

        # Add your shortcut handling logic here

        return {'status': 'shortcut_handled'}

    def run(self):
        """Run the Flask application"""
        port = int(os.environ.get('PORT', 5000))
        debug = os.environ.get('FLASK_ENV') == 'development'

        logger.info(f"Starting Slack Bot server on port {port}")
        logger.info(f"Debug mode: {debug}")

        self.app.run(
            host='0.0.0.0',
            port=port,
            debug=debug
        )


def main():
    """Main entry point"""
    try:
        bot_server = SlackBotServer()
        bot_server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
