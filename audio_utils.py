# audio_utils.py
from gtts import gTTS
import subprocess
import os
import sys # Import sys for platform-specific checks

def text_to_speech(text, filename="output.mp3"):
    """
    Converts text to speech using Google Text-to-Speech (gTTS).
    
    Args:
        text (str): The text to convert.
        filename (str): The desired output filename for the MP3.

    Returns:
        str: The filename if successful, None otherwise.
    """
    if not text:
        print("TTS error: No text provided.")
        return None
    try:
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(filename)
        print(f"Text converted to speech and saved as '{filename}'")
        return filename
    except Exception as e:
        print(f"TTS error: Failed to generate speech for text '{text[:50]}...': {e}")
        return None

def play_audio_to_virtual_mic(audio_filepath, virtual_mic_name):
    """
    Plays an audio file to a specified virtual microphone using ffplay (part of FFmpeg).
    
    Args:
        audio_filepath (str): Path to the audio file (e.g., MP3).
        virtual_mic_name (str): The exact name of the virtual microphone device.
                                 On Windows, use the full DirectShow device name 
                                 (e.g., "CABLE Input (VB-Audio Virtual Cable)").
                                 On Linux, this might be an ALSA or PulseAudio sink name.
                                 On macOS, an aggregate device name or loopback.

    Returns:
        subprocess.Popen: The subprocess.Popen object if successful, None otherwise.
        Requires ffplay to be installed and in system PATH.
    """
    if not os.path.exists(audio_filepath):
        print(f"Error: Audio file not found: {audio_filepath}")
        return None

    if not virtual_mic_name:
        print("Error: Virtual microphone name not provided.")
        return None

    command = ["ffplay"]

    # Platform-specific audio output configuration
    if sys.platform == "win32":
        # Use DirectShow for Windows
        command.extend([
            "-f", "dshow",
            "-i", f"audio={virtual_mic_name}"
        ])
    elif sys.platform == "darwin": # macOS
        # On macOS, you might use 'coreaudio' or similar. 
        # The device name depends on your setup (e.g., aggregate device).
        # This is a placeholder; actual device mapping might be more complex.
        command.extend([
            "-f", "coreaudio",
            "-i", f"{virtual_mic_name}" 
            # Often, device mapping on macOS needs -ac 2 (stereo) or specific device IDs.
            # You might need to adjust based on 'ffmpeg -hide_banner -f avfoundation -list_devices true -i ""'
        ])
    elif sys.platform.startswith("linux"):
        # Use ALSA or PulseAudio. PulseAudio is generally preferred.
        # Ensure you specify the correct sink. `pactl list sinks short` can help.
        # Example: "-f", "pulse", "-i", virtual_mic_name
        command.extend([
            "-f", "pulse", # Or "alsa"
            "-i", virtual_mic_name
        ])
    else:
        print(f"Warning: Unsupported operating system for direct audio device routing: {sys.platform}")
        print("Attempting generic ffplay command, but it may not route to the virtual mic correctly.")
        # Fallback to a simpler command if platform is not explicitly handled
        # This might play to default system output instead of the virtual mic
        command.extend([
            "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo[out];amovie={audio_filepath}:loop=0[in];[in]volume=1[in];[in][out]amerge[a]",
            "-acodec", "pcm_s16le", # Or 'aac' for better compatibility
            "-f", "pulse", # Generic PulseAudio sink, if that's the default
            "-i", virtual_mic_name
        ])
    
    # Add input file and general ffplay options
    command.extend([
        "-i", audio_filepath,
        "-nodisp",      # Don't display video
        "-autoexit",    # Exit when audio finishes
        "-loglevel", "quiet" # Suppress ffplay console output
    ])
    
    print(f"Executing ffplay command: {' '.join(command)}") # Debug print

    DEVNULL = open(os.devnull, 'w')
    process = None
    try:
        process = subprocess.Popen(command, stdout=DEVNULL, stderr=DEVNULL)
        print(f"Started audio playback to virtual mic (PID: {process.pid}).")
        return process
    except FileNotFoundError:
        print("Error: 'ffplay' not found. Please install FFmpeg and ensure 'ffplay' is in your system's PATH.")
        return None
    except Exception as e:
        print(f"Error playing audio to virtual mic: {e}")
        return None
    finally:
        # It's better to close DEVNULL here or use a context manager if possible
        # For Popen, the file handle should remain open as long as the process is running.
        # This needs careful management in the calling code if process is long-lived.
        # For short-lived processes like this, leaving it open might be fine, but explicit close is cleaner.
        # However, Popen keeps the handle open; closing it immediately would break redirect.
        # The calling code should wait for process.wait() and then close.
        pass # Keep DEVNULL open until process finishes or is terminated by calling code.

# Example Usage (for testing purposes, if you uncomment)
if __name__ == "__main__":
    test_text = "Hello, this is a test from the updated audio utilities script. I hope this works."
    test_audio_file = "test_output.mp3"

    # 1. Test Text-to-Speech
    print("\n--- Testing Text-to-Speech ---")
    generated_file = text_to_speech(test_text, test_audio_file)

    if generated_file:
        print(f"Generated: {generated_file}")

        # 2. Test Play Audio to Virtual Mic
        print("\n--- Testing Play Audio to Virtual Mic ---")
        # IMPORTANT: Replace "Your Virtual Microphone Name" with your actual virtual mic name.
        # On Windows, it could be "CABLE Input (VB-Audio Virtual Cable)"
        # On Linux, it could be "pactl list sinks short" output like "virtmic"
        # On macOS, it could be an aggregate device or loopback device name.
        
        # To find names:
        # Windows: `ffplay -f dshow -list_devices true -i dummy`
        # Linux (PulseAudio): `pactl list sinks short` or `pw-top` (PipeWire)
        # macOS: `ffmpeg -hide_banner -f avfoundation -list_devices true -i "" `

        # Placeholder for your actual virtual mic name
        # If you don't have one, this part will likely fail.
        # Set to None if you don't want to run this test or don't know the name.
        MY_VIRTUAL_MIC = "CABLE Input (VB-Audio Virtual Cable)" # <-- CHANGE THIS
        # MY_VIRTUAL_MIC = "VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)" # <-- OR THIS
        # MY_VIRTUAL_MIC = "null" # Use "null" on Linux for a silent output test or default
        # MY_VIRTUAL_MIC = None # Set to None to skip this test

        if MY_VIRTUAL_MIC:
            print(f"Attempting to play '{generated_file}' to '{MY_VIRTUAL_MIC}'...")
            playback_process = play_audio_to_virtual_mic(generated_file, MY_VIRTUAL_MIC)
            if playback_process:
                print("Playback started. Waiting for it to finish (or press Ctrl+C to stop early)...")
                try:
                    playback_process.wait() # Wait for the ffplay process to complete
                    print("Playback finished.")
                except KeyboardInterrupt:
                    print("\nPlayback interrupted.")
                    if playback_process.poll() is None: # Check if process is still running
                        playback_process.terminate() # Terminate ffplay process
                        playback_process.wait()
                    print("FFplay process terminated.")
                finally:
                    # Clean up DEVNULL file handle after process
                    if hasattr(playback_process, '_devnull_file'): # If we stored it
                         playback_process._devnull_file.close()

            else:
                print("Failed to start audio playback.")
        else:
            print("Skipping audio playback test: MY_VIRTUAL_MIC not set.")
    else:
        print("Skipping audio playback test: Text-to-Speech failed.")

    # Clean up generated audio file
    if os.path.exists(test_audio_file):
        try:
            os.remove(test_audio_file)
            print(f"Cleaned up {test_audio_file}")
        except Exception as e:
            print(f"Error cleaning up file {test_audio_file}: {e}")