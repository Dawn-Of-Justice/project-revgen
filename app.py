from gevent import monkey
monkey.patch_all()

from flask import Flask, request, jsonify, redirect
from flask_socketio import SocketIO, emit
from werkzeug.middleware.proxy_fix import ProxyFix
from google.cloud import speech_v1, translate_v2
import os
import json
import io
import wave
from datetime import datetime

# Setup Google Cloud credentials
if 'GOOGLE_CREDENTIALS' in os.environ:
    try:
        credentials_info = json.loads(os.environ['GOOGLE_CREDENTIALS'])
        credentials_path = '/tmp/google-credentials.json'
        with open(credentials_path, 'w') as f:
            json.dump(credentials_info, f)
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        print(f"Credentials file created at {credentials_path}")
    except Exception as e:
        print(f"Error setting up credentials: {str(e)}")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

# Initialize SocketIO with WebSocket transport
socketio = SocketIO(app, 
                   cors_allowed_origins="*", 
                   async_mode='gevent',
                   transport='websocket')

def process_audio_data(audio_data):
    try:
        # Create WAV from raw audio data
        wav_data = io.BytesIO()
        with wave.open(wav_data, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_data)

        # Initialize Google Cloud clients
        speech_client = speech_v1.SpeechClient()
        translate_client = translate_v2.Client()

        # Configure speech recognition
        audio = speech_v1.RecognitionAudio(content=wav_data.getvalue())
        config = speech_v1.RecognitionConfig(
            language_code="ml-IN",
            sample_rate_hertz=16000,
            audio_channel_count=1,
            enable_automatic_punctuation=True
        )

        # Perform speech recognition
        response = speech_client.recognize(config=config, audio=audio)
        
        if not response.results:
            return {"error": "No speech detected"}

        # Get Malayalam text and translate
        malayalam_text = response.results[0].alternatives[0].transcript
        translation = translate_client.translate(
            malayalam_text,
            target_language='en'
        )

        translated_text = translation['translatedText'].lower()
        print(f"Translated text: {translated_text}")
        
        return {
            "original_text": malayalam_text,
            "translated_text": translated_text,
        }
    except Exception as e:
        print(f"Error processing audio: {str(e)}")
        return {"error": str(e)}

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'message': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('audio')
def handle_audio(data):
    print("Received audio data")
    result = process_audio_data(data)
    emit('result', result)

# Keep existing HTTP endpoints
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "voice-command-processor"
    })

@app.route('/process', methods=['POST'])
def process_audio():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    result = process_audio_data(audio_file.read())
    return jsonify(result)

if __name__ == '__main__':
    socketio.run(app, debug=True)