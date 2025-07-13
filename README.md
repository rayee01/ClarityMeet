# 🤖 ClarityMeet – AI-Powered Meeting Assistant

ClarityMeet is an AI-enhanced virtual meeting tool that helps you transcribe, summarize, and voice-enable your meetings using Google Gemini and Whisper. It transforms typed or spoken input into intelligent responses — and can even speak them out loud via a virtual mic.

---

## 🚀 Features

- 🎙️ **Live Voice-to-Text Transcription** using Whisper
- 🧠 **Google Gemini Integration** for response generation
- 🔁 Multiple Interaction Modes: Repeat, Paraphrase, Explain
- 🔊 **Text-to-Speech Playback** using gTTS
- 🎧 **Virtual Mic Output** (e.g., VB-Cable or VoiceMeeter)
- 📝 **Minutes of Meeting (MoM)** generation
- 📤 **Audio File Upload** for offline transcription
- 💬 **Chat History** tracking
- ✨ **Custom UI with Dark Theme (CSS)**

---

## 🛠️ Technologies Used

- Python 3.10+
- [Streamlit](https://streamlit.io)
- [Google Gemini API](https://ai.google.dev)
- [Whisper](https://github.com/openai/whisper)
- [gTTS](https://pypi.org/project/gTTS/)
- [FFmpeg](https://ffmpeg.org/)
- [VB-Cable or VoiceMeeter](https://vb-audio.com/) for virtual mic support

---

## 📦 Installation

```bash
git clone https://github.com/YOUR_USERNAME/ClarityMeet.git
cd ClarityMeet
python -m venv .venv
.venv\Scripts\activate  # On Windows
pip install -r requirements.txt
