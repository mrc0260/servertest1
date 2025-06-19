
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import logging
from transcription_service import process_video_transcription
from gemini_service import handle_chat_request

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
 

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    return handle_chat_request(user_message)

if __name__ == '__main__':
    app.run(debug=True, port=8080)