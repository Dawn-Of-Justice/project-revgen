import pyaudio
import wave
from pydub import AudioSegment
import keyboard
import os
from datetime import datetime

class AudioRecorder:
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.frames = []
        self.recording = False
        
        # Audio settings
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 44100
        self.chunk = 1024

    def callback(self, in_data, frame_count, time_info, status):
        if self.recording:
            self.frames.append(in_data)
        return (in_data, pyaudio.paContinue)

    def record(self):
        # Open stream
        stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
            stream_callback=self.callback
        )

        print("Recording... Press 'q' to stop recording")
        self.recording = True
        stream.start_stream()

        # Wait for 'q' key to stop recording
        keyboard.wait('q')
        
        print("Recording stopped")
        self.recording = False
        
        # Stop and close stream
        stream.stop_stream()
        stream.close()

    def save_recording(self, output_filename=None):
        if not self.frames:
            print("No recording to save!")
            return

        # Generate filename with timestamp if none provided
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"recording"

        # First save as WAV
        wav_filename = f"{output_filename}.wav"
        wf = wave.open(wav_filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.audio.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()

        # Convert to MP3
        mp3_filename = f"{output_filename}.mp3"
        audio = AudioSegment.from_wav(wav_filename)
        audio.export(mp3_filename, format="mp3")

        # Remove temporary WAV file
        os.remove(wav_filename)
        
        print(f"Recording saved as {mp3_filename}")
        
        # Clear frames for next recording
        self.frames = []

    def close(self):
        self.audio.terminate()

def main():
    recorder = AudioRecorder()
    try:
        while True:
            print("\nAudio Recorder Menu:")
            print("1. Start Recording")
            print("2. Exit")
            choice = input("Enter your choice (1-2): ")

            if choice == '1':
                recorder.record()
                recorder.save_recording()
            elif choice == '2':
                break
            else:
                print("Invalid choice. Please try again.")

    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    finally:
        recorder.close()

if __name__ == "__main__":
    main()