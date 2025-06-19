
import logging
from flask import jsonify
from utils import prepare_gemini_prompt, generate_gemini_response

logger = logging.getLogger(__name__)

def handle_chat_request(user_message):
    try:
        logger.debug(f"Received chat message: {user_message}")
        context_prompt = prepare_gemini_prompt(user_message)
        response = generate_gemini_response(context_prompt)
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({'error': f"An error occurred: {str(e)}"}), 500