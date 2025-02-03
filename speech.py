from google.cloud import speech_v1
from google.cloud import translate
import os
from pydub import AudioSegment
import wave

class MalayalamToEnglish:
    def __init__(self, credentials_path):
        """Initialize with Google Cloud credentials"""
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        self.speech_client = speech_v1.SpeechClient()
        self.translate_client = translate.TranslationServiceClient()
        
    def get_project_id(self):
        """Get project ID from credentials file"""
        import json
        with open(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]) as f:
            return json.load(f)["project_id"]
    
    def get_wav_sample_rate(self, wav_path):
        """Get the sample rate from WAV file"""
        with wave.open(wav_path, 'rb') as wav_file:
            return wav_file.getframerate()

    def convert_audio_to_wav(self, audio_path):
        """Convert any audio format to WAV"""
        try:
            audio = AudioSegment.from_file(audio_path)
            wav_path = audio_path.rsplit('.', 1)[0] + '.wav'
            audio.export(wav_path, format='wav')
            return wav_path
        except Exception as e:
            print(f"Error converting audio: {e}")
            return None

    def transcribe_audio(self, audio_path):
        """Transcribe Malayalam audio to text"""
        try:
            # Convert audio to WAV if needed
            if not audio_path.lower().endswith('.wav'):
                audio_path = self.convert_audio_to_wav(audio_path)
                if not audio_path:
                    return "Error: Could not convert audio file"

            # Get sample rate
            sample_rate = self.get_wav_sample_rate(audio_path)

            # Read audio file
            with open(audio_path, 'rb') as audio_file:
                content = audio_file.read()

            # Configure recognition
            audio = speech_v1.RecognitionAudio(content=content)
            config = speech_v1.RecognitionConfig(
                encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=sample_rate,
                language_code='ml-IN',
                enable_automatic_punctuation=True
            )

            # Perform transcription
            response = self.speech_client.recognize(config=config, audio=audio)

            # Combine transcriptions
            transcript = ''
            for result in response.results:
                transcript += result.alternatives[0].transcript + '\n'

            return transcript.strip()

        except Exception as e:
            return f"Error during transcription: {e}"

    def translate_text(self, text):
        """Translate Malayalam text to English"""
        try:
            if not text:
                return "No text to translate"
            
            project_id = self.get_project_id()
            location = 'global'
            parent = f"projects/{project_id}/locations/{location}"
            
            response = self.translate_client.translate_text(
                request={
                    "parent": parent,
                    "contents": [text],
                    "mime_type": "text/plain",
                    "source_language_code": "ml",
                    "target_language_code": "en-US",
                }
            )
            
            return response.translations[0].translated_text
            
        except Exception as e:
            return f"Error during translation: {e}"

    def process_audio(self, audio_path):
        """Complete process: Transcribe Malayalam audio and translate to English"""
        print("Processing audio...")
        print("\nStep 1: Transcribing Malayalam audio...")
        malayalam_text = self.transcribe_audio(audio_path)
        print("Malayalam text:", malayalam_text)
        
        print("\nStep 2: Translating to English...")
        english_text = self.translate_text(malayalam_text)
        print("English translation:", english_text)
        
        return {
            'malayalam': malayalam_text,
            'english': english_text
        }

# Example usage
if __name__ == "__main__":
    # Initialize the translator
    translator = MalayalamToEnglish(r'project-revgen-3929193e6ca4.json')  # Replace with your credentials path
    
    # Process audio file
    results = translator.process_audio(r'C:\Users\salos\project-revgen\recording_20250203_025615.mp3')  # Replace with your audio file path
    
    # Print results
    print("\nFinal Results:")
    print("-------------")
    print("Malayalam:", results['malayalam'])
    print("English:", results['english'])