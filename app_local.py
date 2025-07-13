# app_local.py

import streamlit as st
import os
import subprocess
from datetime import datetime
import psutil
import sounddevice as sd

from whisper_utils import transcribe_audio
from audio_utils import play_audio_to_virtual_mic, text_to_speech
from audio_recorder_streamlit import audio_recorder

import google.generativeai as genai

# --- API Key Handling ---
GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    st.error("🚨 GOOGLE_API_KEY not found in Streamlit secrets.")
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# --- Session Initialization ---
if "messages" not in st.session_state: st.session_state.messages = []
if "last_audio_file" not in st.session_state: st.session_state.last_audio_file = ""
if "generate_clicked" not in st.session_state: st.session_state.generate_clicked = False
if "generated_response_text" not in st.session_state: st.session_state.generated_response_text = ""
if "audio_process_pid" not in st.session_state: st.session_state.audio_process_pid = None
if "live_transcription_text" not in st.session_state: st.session_state.live_transcription_text = ""
if "recording_active" not in st.session_state: st.session_state.recording_active = False
if "uploaded_transcript_output" not in st.session_state:
    st.session_state.uploaded_transcript_output = "Upload an audio file and click 'Transcribe Audio'."

# --- Role Instructions ---
role_contexts = {
    "Repeat": "You are a repeat bot. Repeat the user's message exactly.",
    "Paraphrase": "Paraphrase the user's message within 100 words.",
    "Explain": "Explain the input clearly, directly, under 100 words."
}

# --- Custom CSS Styling ---
def inject_css():
    st.markdown(
        '''
        <style>
        body {background-color: #0C0C0E; color: #E0E0E0;}
        .stApp {background-color: #0C0C0E;}
        .block-container {padding: 2rem 6vw;}
        h1 {color: #6C5CE7; text-align: center;}
        .stButton button {background-color: #6C5CE7; color: white; border: none;}
        .stButton button:hover {background-color: #4B0082;}
        .response-display-container {
            background: #1A1A1E; padding: 20px; border-radius: 8px; text-align: center;
        }
        .transcribe-output-container, .chat-history-container {
            background: #1A1A1E; padding: 16px; border-radius: 8px; max-height: 300px; overflow-y: auto;
        }
        </style>
        ''',
        unsafe_allow_html=True
    )

# --- AI Response Generator ---
def generate_response_with_history(user_input, role_context=None):
    try:
        messages_for_api = [{"role": "user", "parts": [f"{role_context}\n\nUser: {user_input}"]}]
        for msg in st.session_state.messages:
            messages_for_api.append({"role": msg["role"], "parts": [msg["content"]]})
        response = gemini_model.generate_content(messages_for_api)
        full_response_content = response.text

        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.messages.append({"role": "model", "content": full_response_content})
        st.session_state.generated_response_text = full_response_content

        filename = f"response_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
        audio_file_path = text_to_speech(full_response_content, filename)
        st.session_state.last_audio_file = audio_file_path
        return full_response_content
    except Exception as e:
        st.error(f"Gemini error: {e}")
        return None

# --- Audio Control ---
def play_audio_non_blocking(filename, output_device_name):
    if not os.path.exists(filename): return
    process = play_audio_to_virtual_mic(filename, output_device_name)
    if isinstance(process, subprocess.Popen):
        st.session_state.audio_process_pid = process.pid

def stop_audio_non_blocking():
    if st.session_state.audio_process_pid:
        try:
            psutil.Process(st.session_state.audio_process_pid).terminate()
        except: pass
        st.session_state.audio_process_pid = None

# --- UI Setup ---
inject_css()
st.set_page_config(page_title="ClarityMeet", layout="wide")
st.title("ClarityMeet (Local Full Version)")

# --- Input & Audio Columns ---
col1, col2 = st.columns([2,1])

with col1:
    mode = st.selectbox("Interaction Mode:", list(role_contexts.keys()))
    user_prompt = st.text_area("Type your message here:", height=150)
    if st.button("Generate Response"):
        if user_prompt.strip():
            st.session_state.generate_clicked = True
            generate_response_with_history(user_prompt, role_contexts[mode])
        else:
            st.warning("Please enter text first.")

with col2:
    st.markdown("#### Audio Output")
    if st.session_state.last_audio_file and os.path.exists(st.session_state.last_audio_file):
        st.audio(st.session_state.last_audio_file, format="audio/mp3")
    if st.button("▶️ Play to Virtual Mic"):
        play_audio_non_blocking(st.session_state.last_audio_file, "CABLE Input (VB-Audio Virtual Cable)")
    if st.button("⏹ Stop Playback"):
        stop_audio_non_blocking()

# --- Display Response ---
st.subheader("ClarityMeet's Response")
st.markdown(
    f"<div class='response-display-container'>{st.session_state.generated_response_text or 'No response yet.'}</div>",
    unsafe_allow_html=True
)

# --- File Upload & Transcription ---
st.subheader("Upload Audio & Transcribe")
colu1, colu2 = st.columns([1,2])
with colu1:
    audio_file = st.file_uploader("Upload audio file", type=["mp3", "wav", "m4a"])
    if st.button("Transcribe Audio") and audio_file:
        with open("temp_audio.wav", "wb") as f:
            f.write(audio_file.read())
        text = transcribe_audio("temp_audio.wav")
        os.remove("temp_audio.wav")
        st.session_state.uploaded_transcript_output = text or "Transcription failed."

with colu2:
    st.markdown(f"<div class='transcribe-output-container'>{st.session_state.uploaded_transcript_output}</div>", unsafe_allow_html=True)

# --- Chat History Display ---
st.subheader("Chat History")
st.markdown("<div class='chat-history-container'>", unsafe_allow_html=True)
for msg in st.session_state.messages:
    role = "🧑 You" if msg["role"] == "user" else "🤖 ClarityMeet"
    st.markdown(f"**{role}:** {msg['content']}")
st.markdown("</div>", unsafe_allow_html=True)

if st.button("Clear Chat History"):
    st.session_state.messages.clear()
    st.session_state.last_audio_file = ""
    st.session_state.generated_response_text = ""
    st.session_state.uploaded_transcript_output = "Upload an audio file and click 'Transcribe Audio'."
