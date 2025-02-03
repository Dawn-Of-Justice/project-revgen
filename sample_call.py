import requests
import os

def test_audio_processing(audio_file_path):
    url = "YOUR_RENDER_URL/process"
    
    # Prepare the files
    files = {
        'audio': open(audio_file_path, 'rb')
    }
    
    # Make the request
    response = requests.post(url, files=files)
    
    # Print results
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

# Test it
test_audio_processing('path/to/your/audio.wav')