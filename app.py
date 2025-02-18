from flask import Flask, request, jsonify
from google.cloud import speech_v1, translate_v2
import os
import json
from datetime import datetime

app = Flask(__name__)

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

@app.route('/process', methods=['POST'])
def process_audio():
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

       # Read audio content
       audio_content = audio_file.read()

       # Configure speech recognition
       audio = speech_v1.RecognitionAudio(content=audio_content)
       config = speech_v1.RecognitionConfig(
           language_code="ml-IN",
           sample_rate_hertz=16000,
           audio_channel_count=1,
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
       #command = next((cmd for key, cmd in commands.items() if key in translated_text), "UNKNOWN_COMMAND")
       print(translated_text)
       
       return jsonify({
           "original_text": malayalam_text,
           "translated_text": translated_text,
           #"command": command
       })

   except Exception as e:
       return jsonify({
           "error": str(e),
           "type": type(e).__name__
       }), 500
