# app.py
import streamlit as st
import os
from datetime import datetime
import subprocess
import psutil
import sounddevice as sd

# Import modularized functions
from whisper_utils import transcribe_audio
from audio_utils import play_audio_to_virtual_mic, text_to_speech # gTTS is used here

# Install the audio recorder component
from audio_recorder_streamlit import audio_recorder

# --- Google Gemini API Setup (REVERTED FROM DEEPSEEK) ---
import google.generativeai as genai

# Load Google API key from Streamlit Secrets
GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    st.error("🚨 **GOOGLE_API_KEY** not found in Streamlit secrets. Please set it up in `.streamlit/secrets.toml`.")
    st.stop()

# Configure Google Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# Initialize Gemini Pro model
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# --- Session State Initialization ---
# Initialize all necessary session state variables to avoid KeyError on first run
if "messages" not in st.session_state:
    st.session_state.messages = [] # Format: [{"role": "user", "content": "..."}] or [{"role": "model", "content": "..."}]
if "last_audio_file" not in st.session_state:
    st.session_state.last_audio_file = ""
if "generate_clicked" not in st.session_state:
    st.session_state.generate_clicked = False
if "generated_response_text" not in st.session_state:
    st.session_state.generated_response_text = ""
if "audio_process_pid" not in st.session_state: # To store PID of the audio playback process
    st.session_state.audio_process_pid = None
if "live_transcription_text" not in st.session_state:
    st.session_state.live_transcription_text = ""
if "recording_active" not in st.session_state:
    st.session_state.recording_active = False
if "uploaded_transcript_output" not in st.session_state:
    st.session_state.uploaded_transcript_output = "Upload an audio file and click 'Transcribe Audio'."

# --- Mode Prompts for Gemini ---
# The system role content will be dynamic based on the selected mode
role_contexts = {
    "Repeat": "You are a repeat bot. Repeat the user's message exactly, with no changes or commentary.",
    "Paraphrase": "You are a helpful assistant. Paraphrase the user's message clearly and crisply and do not go beyond 100 words.",
    "Explain": "You are a helpful assistant. Answer the following clearly and directly. Do not rephrase or reflect on the user's question. Just answer it and do not go beyond 100 words."
}

# --- Function to Generate AI Response and Convert to Speech ---
def generate_response_with_history(user_input, role_context=None):
    """
    Generates a response from the Google Gemini Pro model, appends to chat history,
    converts the response to speech, and saves the audio file.
    """
    try:
        # Build messages for the API call, including the dynamic system instruction and chat history
        # Gemini API typically starts with user/model pairs. The 'system' prompt
        # for character setting is often pre-pended to the first user query,
        # or handled outside the direct chat history for simpler models like gemini-pro.
        # For a simple chat history:
        messages_for_api = []
        if role_context:
            # Prepend context as a 'user' message with an empty 'model' response
            # to prime the model, or integrate directly into the first message.
            # For simplicity with gemini-pro, we'll often just append it to the current input context
            # or rely on it being the first turn's 'system' like instruction.
            # For this simple case, we'll ensure the role_context influences the prompt directly.
            pass # We'll manage this by adding a system instruction to the prompt directly for simplicity

        for msg in st.session_state.messages:
            # Gemini uses 'user' and 'model' roles
            gemini_role = "user" if msg["role"] == "user" else "model"
            messages_for_api.append({"role": gemini_role, "parts": [msg["content"]]})

        # Add current user input, incorporating the role context
        final_user_prompt = f"{role_context}\n\nUser: {user_input}" if role_context else user_input
        messages_for_api.append({"role": "user", "parts": [final_user_prompt]})
        
        with st.spinner("Thinking... Generating response..."):
            # Ensure the model is called correctly
            response = gemini_model.generate_content(messages_for_api)
            
            full_response_content = response.text # Access response text
        
        # Append user and model messages to session state history
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.messages.append({"role": "model", "content": full_response_content}) # Gemini uses 'model' role for AI responses
        
        # Store the generated text response for display in the UI
        st.session_state.generated_response_text = full_response_content
        
        # Generate a unique filename for the audio response
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"response_{timestamp}.mp3"
        
        # Convert the AI's text response to speech using the modularized function
        audio_file_path = text_to_speech(full_response_content, filename)
        
        if audio_file_path:
            st.session_state.last_audio_file = audio_file_path
        else:
            st.error("Failed to convert response to speech. Check audio_utils.py and gTTS installation.")
        
        return full_response_content
    except Exception as e:
        st.error(f"Error during response generation with Gemini: {e}")
        st.session_state.generated_response_text = f"Error: {e}"
        return None

# --- Function to Generate Minutes of Meeting (MoM) ---
def generate_minutes_of_meeting():
    """
    Generates a summary of the conversation history and live transcription using Google Gemini.
    """
    if not st.session_state.messages and not st.session_state.live_transcription_text:
        return "No conversation history or live transcription to generate minutes."
    
    convo = ""
    # Add chat history to the conversation string
    for m in st.session_state.messages:
        role_label = "User" if m["role"] == "user" else "ClarityMeet" # Changed from 'assistant' to 'ClarityMeet' for display
        convo += f"{role_label}: {m['content']}\n"
    
    # Add live transcription text if available
    if st.session_state.live_transcription_text:
        convo += f"\n--- Live Transcription (Raw) ---\n{st.session_state.live_transcription_text}\n"

    # Define the prompt for MoM generation
    mom_prompt = f"""You are a meeting assistant. Create professional minutes of the meeting (MoM) from the conversation below. Use bullet points, group by topics, and highlight key decisions.

Conversation:
{convo}
"""
    with st.spinner("Generating Minutes of Meeting with Gemini..."):
        try:
            # Gemini expects a list of dictionaries with 'role' and 'parts'
            mom_messages = [
                {"role": "user", "parts": [mom_prompt]}
            ]
            response = gemini_model.generate_content(mom_messages)
            return response.text
        except Exception as e:
            return f"Failed to generate MoM with Gemini: {e}"

# --- Virtual Mic Playback Control Functions ---
def play_audio_non_blocking(filename, output_device_name):
    """
    Starts playing an audio file to a specified virtual microphone in a non-blocking way.
    It expects play_audio_to_virtual_mic to return a subprocess.Popen object.
    """
    if not os.path.exists(filename):
        st.error(f"Audio file not found: {filename}")
        return False
    try:
        # Call the modularized utility function.
        # This function should return a subprocess.Popen object for non-blocking control.
        process = play_audio_to_virtual_mic(filename, output_device_name)
        
        if process:
            # Check if it's a Popen object, then store its PID
            if isinstance(process, subprocess.Popen):
                st.success(f"Playing audio to virtual mic (PID: {process.pid}).")
                st.session_state.audio_process_pid = process.pid
            else:
                # This case should ideally not be hit if audio_utils.py is correctly modified
                st.success("Playing audio to virtual mic (could not get PID for non-blocking control).")
                st.session_state.audio_process_pid = None
            return True
        else:
            st.error("Failed to start audio playback process. Check audio_utils.py setup and FFmpeg installation.")
            return False
    except Exception as e:
        st.error(f"Error initiating audio playback to virtual mic: {e}")
        return False

def stop_audio_non_blocking():
    """
    Stops the audio playback process identified by its PID.
    """
    if st.session_state.audio_process_pid:
        try:
            process = psutil.Process(st.session_state.audio_process_pid)
            process.terminate() # Terminate the process
            st.session_state.audio_process_pid = None # Clear the stored PID
            st.success("Audio playback stopped.")
        except psutil.NoSuchProcess:
            st.info("Audio process already terminated or not found.")
            st.session_state.audio_process_pid = None
        except Exception as e:
            st.error(f"Error stopping audio playback: {e}")
    else:
        st.info("No audio currently playing to virtual mic.")

# --- Custom CSS Injection for Styling ---
def inject_css():
    """Injects custom CSS for a dark theme and improved layout."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

        :root {
            --primary-bg: #0C0C0E;
            --secondary-bg: #1A1A1E;
            --card-bg: #212125;
            --text-color: #E0E0E0;
            --light-text: #A0A0A0;
            --accent-color: #6C5CE7; /* A subtle, modern purple */
            --button-hover: #4B0082; /* Darker purple on hover */
            --border-color: #333338;
            --font-main: 'Inter', sans-serif;
            --font-heading: 'Space Grotesk', sans-serif;
            --shadow-subtle: rgba(0, 0, 0, 0.2);
            --gap-xlarge: 60px; /* Even more space for major sections */
            --gap-large: 40px;
            --gap-medium: 25px;
            --gap-small: 15px;
        }

        body {
            font-family: var(--font-main);
            color: var(--text-color);
            background-color: var(--primary-bg);
            margin: 0;
            padding: 0;
            overflow-x: hidden;
        }

        /* Main Streamlit app container */
        .stApp {
            background-color: var(--primary-bg);
        }

        /* Adjust Streamlit's default padding for full width usage */
        .block-container {
            padding-left: 8vw;
            padding-right: 8vw;
            padding-top: var(--gap-xlarge); /* Push content down from the very top */
            padding-bottom: var(--gap-xlarge);
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: var(--font-heading);
            color: var(--text-color);
            letter-spacing: -0.02em;
            margin-bottom: 0.8rem;
            padding-top: 0;
        }

        h1 {
            font-size: 3rem;
            text-align: center;
            color: var(--accent-color);
            margin-bottom: var(--gap-large); /* More space below main title */
            text-shadow: 0 0 10px rgba(108, 92, 231, 0.3);
            padding-top: 0;
        }

        /* Streamlit Header (for adjusting padding) */
        .st-emotion-cache-18ni7ap {
            padding-top: 0rem;
            padding-bottom: 0rem;
        }

        /* Fix for selectbox styling and dropdown text visibility */
.stSelectbox {
    background-color: var(--secondary-bg) !important;
    color: var(--text-color) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 6px !important;
}

.stSelectbox label {
    color: var(--light-text) !important;
    font-weight: 500;
}

.stSelectbox div[data-baseweb="select"] {
    background-color: var(--secondary-bg) !important;
    color: var(--text-color) !important;
}

        }
        .stTextArea textarea:focus, .stTextInput input:focus, .stSelectbox > div > div:focus-within, .stFileUploader > div > div:focus-within {
            border-color: var(--accent-color);
            box-shadow: 0 0 0 2px rgba(108, 92, 231, 0.3);
            outline: none;
        }
        /* Specific fix for selectbox text color */
        .stSelectbox .st-bd, .stSelectbox .st-be, .stSelectbox .st-df {
            color: var(--text-color) !important;
            font-weight: 500;
        }

        /* Buttons */
        .stButton button {
            background-color: var(--accent-color);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            font-weight: 500;
            letter-spacing: 0.02em;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 2px 5px var(--shadow-subtle);
            margin-top: var(--gap-small);
            margin-right: 10px;
            font-family: var(--font-main);
        }
        .stButton button:hover {
            background-color: var(--button-hover);
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
        }

        /* Modular Containers (Cards) */
        .st-emotion-cache-1cypcdb { /* Generic container for columns */
            background-color: var(--card-bg);
            border-radius: 8px;
            padding: var(--gap-large);
            margin-bottom: var(--gap-medium);
            box-shadow: 0 5px 15px var(--shadow-subtle);
            border: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            height: 100%; /* Ensure columns fill height of row */
        }
        
        /* Ensure columns themselves take up full height */
        .st-emotion-cache-nahz7x { /* Target for st.column wrapper */
            height: 100%;
        }

        /* Main Response Display Area */
        .response-display-container {
            background-color: var(--secondary-bg);
            border-radius: 8px;
            padding: var(--gap-large);
            margin-bottom: var(--gap-large);
            border: 1px solid var(--border-color);
            box-shadow: 0 2px 10px var(--shadow-subtle);
            min-height: 150px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
        }
        .response-display-container p {
            margin: 0;
            font-size: 1.1rem;
            color: var(--text-color);
            line-height: 1.8;
        }
        .response-display-container h3 {
             color: var(--accent-color);
             margin-bottom: var(--gap-small);
        }


        /* Chat History and MoM sections - fixed height with scrolling */
        .chat-history-container, .mom-container, .transcribe-output-container, .live-transcribe-container {
            max-height: 500px;
            overflow-y: auto;
            background-color: var(--secondary-bg);
            border-radius: 8px;
            padding: var(--gap-medium);
            margin-top: var(--gap-medium);
            box-shadow: inset 0 1px 5px var(--shadow-subtle);
            border: 1px solid var(--border-color);
        }
        .chat-history-container::-webkit-scrollbar, .mom-container::-webkit-scrollbar, .transcribe-output-container::-webkit-scrollbar, .live-transcribe-container::-webkit-scrollbar {
            width: 8px;
        }
        .chat-history-container::-webkit-scrollbar-track, .mom-container::-webkit-scrollbar-track, .transcribe-output-container::-webkit-scrollbar-track, .live-transcribe-container::-webkit-scrollbar-track {
            background: var(--secondary-bg);
            border-radius: 10px;
        }
        .chat-history-container::-webkit-scrollbar-thumb, .mom-container::-webkit-scrollbar-thumb, .transcribe-output-container::-webkit-scrollbar-thumb, .live-transcribe-container::-webkit-scrollbar-thumb {
            background-color: var(--border-color);
            border-radius: 10px;
            border: 2px solid var(--secondary-bg);
        }
        .chat-history-container::-webkit-scrollbar-thumb:hover, .mom-container::-webkit-scrollbar-thumb:hover, .transcribe-output-container::-webkit-scrollbar-thumb:hover, .live-transcribe-container::-webkit-scrollbar-thumb:hover {
            background-color: var(--light-text);
        }


        /* Message styling in chat history */
        .stMarkdown p {
            font-size: 0.95rem;
            line-height: 1.7;
            margin-bottom: 0.8rem;
        }
        .stMarkdown strong {
            color: var(--accent-color);
        }
        .stAlert {
            background-color: var(--card-bg);
            color: var(--text-color);
            border-left: 4px solid var(--accent-color);
            border-radius: 4px;
            padding: 12px 18px;
            margin-top: var(--gap-small);
            font-size: 0.9rem;
            line-height: 1.6;
        }

        /* Small text for descriptions */
        .small-text {
            font-size: 0.9em;
            color: var(--light-text);
            margin-bottom: 10px;
        }

        /* Remove default Streamlit elements */
        #MainMenu {
            visibility: hidden;
        }
        footer {
            visibility: hidden;
            height: 0;
        }
        .st-emotion-cache-10o5u35 {
            padding-bottom: 0rem;
            padding-top: 0rem;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

# --- Streamlit UI Layout ---
st.set_page_config(page_title="ClarityMeet", layout="wide", initial_sidebar_state="collapsed")
inject_css()

st.title("ClarityMeet")

# --- Top Row Layout: Input/Generation on Left, Audio Output/Virtual Mic on Right ---
col_left, col_right = st.columns([2, 1]) # Left column wider for input, right for audio

with col_left:
    with st.container():
        st.subheader("Your Input")
        st.markdown('<div class="small-text">Select a mode and type your message.</div>', unsafe_allow_html=True)
        
        # Mode Selection as a small subhead within Your Input
        mode = st.selectbox("Interaction Mode:", list(role_contexts.keys()), key="mode_select")
        role = role_contexts.get(mode)

        user_prompt = st.text_area("Type your message here:", height=150, key="user_input_text", placeholder="Enter your text for ClarityMeet...", label_visibility="collapsed")
        
        if st.button("Generate Response", key="generate_response_btn"):
            if user_prompt.strip():
                st.session_state.generate_clicked = True
                generate_response_with_history(user_prompt.strip(), role_context=role)
            else:
                st.warning("Please enter some text to generate a response.")
                st.session_state.generate_clicked = False # Reset if no input
                st.session_state.generated_response_text = "" # Clear previous response

with col_right:
    with st.container():
        st.subheader("Audio Output")
        st.markdown('<div class="small-text">Hear ClarityMeet\'s last response.</div>', unsafe_allow_html=True)
        
        # Small audio output for direct playback in Streamlit
        if st.session_state.last_audio_file and os.path.exists(st.session_state.last_audio_file):
            st.audio(st.session_state.last_audio_file, format="audio/mp3", start_time=0)
        else:
            st.info("Generated audio will appear here.")
        
        st.markdown(f'<div style="margin-top: var(--gap-small);"></div>', unsafe_allow_html=True) # Spacer
        st.subheader("Virtual Mic Control")
        st.markdown('<div class="small-text">Play/Stop AI\'s last response to your virtual microphone.</div>', unsafe_allow_html=True)

        col_play, col_stop = st.columns(2)
        with col_play:
            # --- IMPORTANT: Pass the FULL, EXACT playback device name here ---
            # For VB-Cable: "CABLE Input (VB-Audio Virtual Cable)"
            # For VoiceMeeter: "VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)"
            # Find this name by running `ffplay -f dshow -list_devices true -i dummy` in your terminal
            # Look under "DirectShow audio devices" for a device with "(output)" capabilities.
            VIRTUAL_PLAYBACK_DEVICE_NAME = "CABLE Input (VB-Audio Virtual Cable)" # <<<<< ADJUST THIS IF USING VOICEMEETER OR DIFFERENT CABLE NAME
            
            if st.button("▶️ Play to Virtual Mic", key="play_virtual_mic_btn"):
                filename = st.session_state.last_audio_file
                if filename and os.path.exists(filename):
                    play_audio_non_blocking(filename, VIRTUAL_PLAYBACK_DEVICE_NAME)
                else:
                    st.error("No audio generated yet to play to virtual mic.")
        with col_stop:
            if st.button("⏹ Stop Virtual Mic Playback", key="stop_virtual_mic_btn"):
                stop_audio_non_blocking()


# --- ClarityMeet's Response Section (Below the top columns) ---
st.markdown(f'<div style="margin-top: var(--gap-large);"></div>', unsafe_allow_html=True) # Large spacer
st.subheader("ClarityMeet's Response")

# Determine the content to display inside the box
response_content = ""
if st.session_state.generated_response_text:
    response_content = f"<p>{st.session_state.generated_response_text}</p>"
elif st.session_state.generate_clicked: # If button was clicked but no response (e.g., error)
    response_content = '<p style="color: #FF6347; font-weight: bold;">An error occurred during response generation. Please try again.</p>'
else:
    response_content = '<p style="color: var(--light-text);">Your AI-generated response will appear here after clicking \'Generate Response\'.</p>'

# Now, embed the determined content directly within the HTML div
st.markdown(
    f'<div class="response-display-container">{response_content}</div>',
    unsafe_allow_html=True
)

st.markdown(f'<div style="margin-top: var(--gap-large);"></div>', unsafe_allow_html=True) # Spacer before Live Transcription
st.subheader("Live Meeting Transcription")
st.markdown('<div class="small-text">Real-time transcription of audio captured from your selected microphone.</div>', unsafe_allow_html=True)

# Placeholder for live transcription output
live_transcription_placeholder = st.empty()
live_transcription_placeholder.markdown(
    f'<div class="live-transcribe-container"><p>{st.session_state.live_transcription_text if st.session_state.live_transcription_text else "Start live recording to see transcription here..."}</p></div>',
    unsafe_allow_html=True
)

# --- UNCOMMENT THE BLOCK BELOW TO SEE YOUR AUDIO DEVICE IDs ---
# This will help you find the correct VIRTUAL_MIC_RECORDING_DEVICE_ID for recording
# and the VIRTUAL_PLAYBACK_DEVICE_NAME for playing audio.
# Run your Streamlit app, check the output in the app for device names and their indices.
# Then, update VIRTUAL_MIC_RECORDING_DEVICE_ID and VIRTUAL_PLAYBACK_DEVICE_NAME above.
# try:
#     st.markdown("---")
#     st.subheader("Audio Device Information (for troubleshooting)")
#     st.text("Below is a list of all detected audio devices and their indices.")
#     st.text("For 'Play to Virtual Mic', look for a PLAYBACK device like 'CABLE Input (VB-Audio Virtual Cable)' or 'VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)'. Note its FULL name.")
#     st.text("For 'Toggle Live Recording', look for a RECORDING device like 'CABLE Output (VB-Audio Virtual Cable)' or 'VoiceMeeter Output (VB-Audio VoiceMeeter VAIO)'. Note its NUMERICAL INDEX.")
#     devices = sd.query_devices()
#     device_info_str = ""
#     for i, device in enumerate(devices):
#         device_info_str += f"Index {i}: Name='{device['name']}', Input Channels={device['max_input_channels']}, Output Channels={device['max_output_channels']}\n"
#     st.text(device_info_str)
#     st.markdown("---")
# except Exception as e:
#     st.warning(f"Could not list audio devices: {e}. Ensure 'sounddevice' is installed (`pip install sounddevice`).")


if st.button("Toggle Live Recording", key="toggle_live_recording_btn"):
    st.session_state.recording_active = not st.session_state.recording_active
    if not st.session_state.recording_active:
        st.info("Live recording stopped. Finalizing transcription...")
    else:
        st.success("Recording live audio... (Speak into your microphone or ensure meeting audio is routed to virtual mic)")
    st.rerun() # Rerun to update button state and start/stop recorder


if st.session_state.recording_active:
    # --- IMPORTANT: YOU MUST REPLACE 'None' BELOW WITH THE ACTUAL NUMERICAL ID ---
    # Find this ID by UNCOMMENTING the "Audio Device Information" block above,
    # running your Streamlit app, and looking at the output for "CABLE Output"
    # or "VoiceMeeter Output" that has max_input_channels > 0.
    VIRTUAL_MIC_RECORDING_DEVICE_ID = None # <<<<<<<<<<<<<<<< CHANGE THIS TO YOUR ACTUAL DEVICE ID (e.g., 3) <<<<<<<<<<<<<<<<
    # Example: VIRTUAL_MIC_RECORDING_DEVICE_ID = 3

    audio_bytes = audio_recorder(
        text="", 
        pause_threshold=1.5,
        energy_threshold=(-1.0, 1.0),
        sample_rate=16000,
        device_id=VIRTUAL_MIC_RECORDING_DEVICE_ID, # <<< This is the crucial line for virtual mic input
        key="live_audio_recorder"
    )

    if audio_bytes: # This block executes when audio_recorder_streamlit provides a chunk
        # Save ONLY the current chunk to a temporary file for Whisper processing
        temp_live_audio_path = "temp_live_meeting_audio_chunk.wav"
        try:
            with open(temp_live_audio_path, "wb") as f:
                f.write(audio_bytes) # Write only the current chunk received

            # Transcribe the current audio chunk
            live_transcript_chunk = transcribe_audio(temp_live_audio_path)
            os.remove(temp_live_audio_path) # Clean up the temporary file immediately

            if live_transcript_chunk and live_transcript_chunk.strip():
                new_text = live_transcript_chunk.strip()
                # Append to session state, adding a space if needed for readability
                if st.session_state.live_transcription_text and not st.session_state.live_transcription_text.endswith(" ") and not new_text.startswith(" "):
                    st.session_state.live_transcription_text += " " + new_text
                else:
                    st.session_state.live_transcription_text += new_text

                # Update the placeholder directly to show the new transcription
                live_transcription_placeholder.markdown(
                    f'<div class="live-transcribe-container"><p>{st.session_state.live_transcription_text}</p></div>',
                    unsafe_allow_html=True
                )
        except Exception as e:
            st.warning(f"Error processing live audio chunk: {e}")
            if os.path.exists(temp_live_audio_path):
                os.remove(temp_live_audio_path)

# --- Transcribe Audio from Files ---
st.markdown(f'<div style="margin-top: var(--gap-large);"></div>', unsafe_allow_html=True) # Large spacer
st.subheader("Transcribe Audio from Files")
st.markdown('<div class="small-text">Upload an audio file (WAV, MP3, M4A) to get a transcription using Whisper.</div>', unsafe_allow_html=True)

transcribe_col1, transcribe_col2 = st.columns([1,2]) # Give more space to transcription output

with transcribe_col1:
    audio_upload = st.file_uploader("Upload an audio file:", type=["wav", "mp3", "m4a"], key="audio_uploader", label_visibility="collapsed")
    if st.button("Transcribe Uploaded Audio", key="transcribe_audio_btn") and audio_upload:
        with st.spinner("Transcribing audio..."):
            try:
                # Create a temporary file with the correct extension
                temp_upload_path = "uploaded_audio_for_transcription" + os.path.splitext(audio_upload.name)[1]
                with open(temp_upload_path, "wb") as f:
                    f.write(audio_upload.read())
                
                # Call the modularized transcription function
                transcript = transcribe_audio(temp_upload_path)
                os.remove(temp_upload_path) # Clean up temp file

                if transcript:
                    st.session_state.uploaded_transcript_output = transcript # Store transcript in session state
                    st.success("Transcription complete!")
                else:
                    st.error("Failed to transcribe audio. Please try another file or check Whisper installation.")
                    st.session_state.uploaded_transcript_output = "No transcription available."
            except Exception as e:
                st.error(f"Error during transcription: {e}")
                st.session_state.uploaded_transcript_output = f"Error: {e}"
    # Display initial message or previous transcript
    elif "uploaded_transcript_output" not in st.session_state:
        st.session_state.uploaded_transcript_output = "Upload an audio file and click 'Transcribe Audio'."

with transcribe_col2:
    st.markdown('<div class="small-text">Uploaded Audio Transcription Output:</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="transcribe-output-container"><p>{st.session_state.uploaded_transcript_output}</p></div>', unsafe_allow_html=True)


# --- Minutes of Meeting & Chat History (Bottom Sections) ---
st.markdown(f'<div style="margin-top: var(--gap-xlarge);"></div>', unsafe_allow_html=True) # Even larger spacer

mom_col, chat_col = st.columns(2)

with mom_col:
    st.subheader("Minutes of Meeting")
    st.markdown('<div class="small-text">Generate a summary of your conversation and live transcription.</div>', unsafe_allow_html=True)
    if st.button("Generate MoM Summary", key="generate_mom_btn"):
        mom = generate_minutes_of_meeting()
        st.markdown(f"<div class='mom-container'><h4>Summary Overview</h4><p>{mom}</p></div>", unsafe_allow_html=True)
    else:
        st.info("Click 'Generate MoM Summary' to get a concise overview of your meeting.")

with chat_col:
    st.subheader("Chat History")
    st.markdown('<div class="small-text">Review your past interactions with ClarityMeet.</div>', unsafe_allow_html=True)
    st.markdown("<div class='chat-history-container'>", unsafe_allow_html=True)
    if st.session_state.messages:
        for msg in st.session_state.messages:
            # Adjust role display for Gemini's 'model' role
            role_display = "🧑 You" if msg["role"] == "user" else "🤖 ClarityMeet"
            st.markdown(f"**{role_display}:** {msg['content']}")
    else:
        st.info("No messages yet. Start a conversation!")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown(f'<div style="margin-top: var(--gap-large);"></div>', unsafe_allow_html=True)
# Clear History Button at the very bottom, full width
if st.button("Clear All Conversation, Live Transcription & Audio History", key="clear_all_history_btn", use_container_width=True):
    st.session_state.messages = []
    st.session_state.live_transcription_text = ""
    st.session_state.recording_active = False
    st.session_state.last_audio_file = ""
    st.session_state.generated_response_text = ""
    st.session_state.uploaded_transcript_output = "Upload an audio file and click 'Transcribe Audio'." # Reset uploaded transcript
    if st.session_state.audio_process_pid:
        stop_audio_non_blocking() # Try to stop any ongoing playback
    st.rerun() # Rerun the app to reflect cleared state