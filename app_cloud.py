# app_cloud.py (Streamlit Cloud-Safe Version)
import streamlit as st
import os
from datetime import datetime

# Import modularized functions
from whisper_utils import transcribe_audio
from audio_utils import text_to_speech  # gTTS is used here
from audio_recorder_streamlit import audio_recorder

# --- Google Gemini API Setup ---
import google.generativeai as genai

# Load Google API key from Streamlit Secrets
GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    st.error("🚨 GOOGLE_API_KEY not found in Streamlit secrets.")
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# Session state variables
for key, default in {
    "messages": [],
    "last_audio_file": "",
    "generate_clicked": False,
    "generated_response_text": "",
    "live_transcription_text": "",
    "recording_active": False,
    "uploaded_transcript_output": "Upload an audio file and click 'Transcribe Audio'."
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Interaction modes
role_contexts = {
    "Repeat": "You are a repeat bot. Repeat the user's message exactly.",
    "Paraphrase": "Paraphrase the user's message clearly and crisply.",
    "Explain": "Explain the user's message simply and clearly."
}

# Response generation function
def generate_response_with_history(user_input, role_context=None):
    try:
        messages_for_api = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
            for m in st.session_state.messages
        ]
        full_prompt = f"{role_context}\n\nUser: {user_input}" if role_context else user_input
        messages_for_api.append({"role": "user", "parts": [full_prompt]})

        with st.spinner("Generating response..."):
            response = gemini_model.generate_content(messages_for_api)
            output_text = response.text

        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.messages.append({"role": "model", "content": output_text})
        st.session_state.generated_response_text = output_text

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"response_{timestamp}.mp3"
        st.session_state.last_audio_file = text_to_speech(output_text, filename)

        return output_text
    except Exception as e:
        st.session_state.generated_response_text = f"Error: {e}"
        return None

# MoM generation
def generate_minutes_of_meeting():
    convo = "".join([
        f"{'User' if m['role'] == 'user' else 'ClarityMeet'}: {m['content']}\n"
        for m in st.session_state.messages
    ])
    if st.session_state.live_transcription_text:
        convo += f"\n--- Live Transcription (Raw) ---\n{st.session_state.live_transcription_text}\n"

    mom_prompt = f"""You are a meeting assistant. Create professional minutes of the meeting (MoM)
from the conversation below. Use bullet points, group by topics, and highlight key decisions.\n\nConversation:\n{convo}"""

    with st.spinner("Generating MoM..."):
        try:
            response = gemini_model.generate_content([{"role": "user", "parts": [mom_prompt]}])
            return response.text
        except Exception as e:
            return f"MoM Error: {e}"

# --- UI ---
st.set_page_config("ClarityMeet", layout="wide")
st.title("ClarityMeet (Cloud Version)")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Your Input")
    mode = st.selectbox("Interaction Mode:", list(role_contexts.keys()), key="mode_select")
    role = role_contexts.get(mode)
    user_prompt = st.text_area("Type your message here:", height=150, key="user_input_text")

    if st.button("Generate Response"):
        if user_prompt.strip():
            st.session_state.generate_clicked = True
            generate_response_with_history(user_prompt.strip(), role_context=role)
        else:
            st.warning("Enter some text to generate a response.")

with col2:
    st.subheader("Audio Output")
    if st.session_state.last_audio_file and os.path.exists(st.session_state.last_audio_file):
        st.audio(st.session_state.last_audio_file, format="audio/mp3")
    else:
        st.info("Response audio will appear here.")

st.subheader("ClarityMeet's Response")
if st.session_state.generated_response_text:
    st.success(st.session_state.generated_response_text)

st.subheader("Live Meeting Transcription")
st.markdown(st.session_state.live_transcription_text or "(Live transcription will appear here...)")

# File transcription
st.subheader("Transcribe Audio from File")
audio_upload = st.file_uploader("Upload audio file (WAV/MP3/M4A):", type=["wav", "mp3", "m4a"])
if st.button("Transcribe Uploaded Audio") and audio_upload:
    try:
        ext = os.path.splitext(audio_upload.name)[1]
        temp_path = f"uploaded_audio{ext}"
        with open(temp_path, "wb") as f:
            f.write(audio_upload.read())
        transcript = transcribe_audio(temp_path)
        os.remove(temp_path)
        st.session_state.uploaded_transcript_output = transcript or "No transcription."
    except Exception as e:
        st.session_state.uploaded_transcript_output = f"Transcription Error: {e}"

st.markdown(st.session_state.uploaded_transcript_output)

# MoM & Chat
st.subheader("Minutes of Meeting")
if st.button("Generate MoM Summary"):
    mom = generate_minutes_of_meeting()
    st.markdown(mom)

st.subheader("Chat History")
for msg in st.session_state.messages:
    st.markdown(f"**{'🧑 You' if msg['role'] == 'user' else '🤖 ClarityMeet'}:** {msg['content']}")

# Clear all
if st.button("Clear All"):
    for key in ["messages", "live_transcription_text", "last_audio_file",
                "generated_response_text", "uploaded_transcript_output"]:
        st.session_state[key] = [] if isinstance(st.session_state[key], list) else ""
    st.success("Cleared session data.")
