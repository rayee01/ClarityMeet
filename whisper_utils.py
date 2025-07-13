# whisper_utils.py
import whisper
import os

# Load the Whisper model once when the script starts
# 'base.en' is good for English-only, or use 'base' for multi-language.
# The model will be downloaded to ~/.cache/whisper if not already present.
print("Loading Whisper model (this may take a moment and download files if first run)...")
try:
    model = whisper.load_model("base.en") # Using 'base.en' as per your last update
    print("Whisper model loaded successfully.")
except Exception as e:
    print(f"Error loading Whisper model: {e}")
    print("Please ensure 'openai-whisper' is installed (`pip install openai-whisper`) and check your internet connection for initial download.")
    model = None # Set model to None if loading fails

def transcribe_audio(audio_file_path):
    """
    Transcribes an audio file using OpenAI's Whisper model.
    """
    if not os.path.exists(audio_file_path):
        print(f"Transcription Error: Audio file not found at {audio_file_path}")
        return None
    
    if model is None:
        print("Transcription Error: Whisper model failed to load at startup. Cannot transcribe.")
        return None

    try:
        print(f"Attempting to transcribe audio file: {audio_file_path}") # Debug print
        result = model.transcribe(audio_file_path)
        transcript = result.get("text") # Using .get() as per your update
        print(f"Transcription result: {transcript}") # Debug print
        return transcript
    except Exception as e:
        print(f"Whisper transcription error during processing: {e}") # Debug print: Shows the specific Whisper error
        print("Please ensure FFmpeg is installed and in your system PATH for audio processing.")
        return None