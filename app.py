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

# Setup Google Cloud credentials from environment variable
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
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
socketio = SocketIO(app, cors_allowed_origins="*")

@app.before_request
def before_request():
    # Redirect HTTP to HTTPS
    if not request.is_secure:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

# Configuration
ALLOWED_AUDIO_EXTENSIONS = {'wav', 'mp3', 'm4a'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "voice-command-processor"
    })

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'message': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# This will handle the binary audio data
@socketio.on('message')
def handle_binary_audio(data):
    try:
        # Convert binary audio data to WAV format
        audio_data = io.BytesIO()
        with wave.open(audio_data, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(data)

        # Initialize Google Cloud clients
        speech_client = speech_v1.SpeechClient()
        translate_client = translate_v2.Client()

        # Configure speech recognition
        audio = speech_v1.RecognitionAudio(content=audio_data.getvalue())
        config = speech_v1.RecognitionConfig(
            language_code="ml-IN",
            sample_rate_hertz=16000,
            audio_channel_count=1,
            enable_automatic_punctuation=True
        )

        # Perform speech recognition
        response = speech_client.recognize(config=config, audio=audio)
        
        if response.results:
            # Get Malayalam text
            malayalam_text = response.results[0].alternatives[0].transcript

            # Translate to English
            translation = translate_client.translate(
                malayalam_text,
                target_language='en'
            )

            translated_text = translation['translatedText'].lower()
            print(f"Translated text: {translated_text}")
            
            # Send results back to client
            emit('transcription', {
                'original_text': malayalam_text,
                'translated_text': translated_text,
            })
        else:
            emit('error', {'message': 'No speech detected'})

    except Exception as e:
        print(f"Error processing audio: {str(e)}")
        emit('error', {'message': str(e), 'type': type(e).__name__})

@app.route('/process', methods=['POST'])
def process_audio():
    print("Processing audio file...")
    try:
        # Check if audio file is present
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400
        
        audio_file = request.files['audio']
        if not allowed_file(audio_file.filename):
            return jsonify({"error": "Invalid file format"}), 400
                      
        # Initialize Google Cloud clients
        speech_client = speech_v1.SpeechClient()
        translate_client = translate_v2.Client()

        # Read audio content directly from the request stream
        audio_content = audio_file.read()

        # Configure speech recognition
        audio = speech_v1.RecognitionAudio(content=audio_content)
        config = speech_v1.RecognitionConfig(
            language_code="ml-IN",
            sample_rate_hertz=16000,  # Match ESP32 sample rate
            audio_channel_count=1,     # Mono
            enable_automatic_punctuation=True
        )

        # Perform speech recognition
        response = speech_client.recognize(config=config, audio=audio)
        
        if not response.results:
            return jsonify({"error": "No speech detected"}), 400

        # Get Malayalam text
        malayalam_text = response.results[0].alternatives[0].transcript

        # Translate to English
        translation = translate_client.translate(
            malayalam_text,
            target_language='en'
        )

        translated_text = translation['translatedText'].lower()
        print(f"Translated text: {translated_text}")
        return jsonify({
            "original_text": malayalam_text,
            "translated_text": translated_text,
        })

    except Exception as e:
        print(f"Error processing request: {str(e)}")  # Server-side logging
        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 500
