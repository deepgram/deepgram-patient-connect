# Patient Connect — Voice AI Demo

A real-time voice agent that makes outbound calls to patients about prescription savings programs. Built for the **Deepgram + AWS webinar** demonstrating Deepgram STT/TTS on Amazon SageMaker with Amazon Bedrock.

## Architecture

```
Browser Mic (16kHz PCM) ──► WebSocket ──► Deepgram Flux STT (SageMaker)
                                              │
                                              ▼
                                         Amazon Bedrock
                                        (Claude Haiku)
                                              │
                                              ▼
Browser Speaker (24kHz PCM) ◄── WebSocket ◄── Deepgram Aura-2 TTS (SageMaker)
```

| Component | Technology |
|-----------|-----------|
| **STT** | Deepgram Flux on SageMaker (`deepgram-sagemaker` 0.2.2) |
| **TTS** | Deepgram Aura-2 on SageMaker (`deepgram-sagemaker` 0.2.2) |
| **LLM** | Amazon Bedrock — Claude Haiku (Converse API) |
| **Server** | Python `websockets` + `asyncio` |
| **Client** | React + Vite + raw WebSocket + Web Audio API |

## Prerequisites

- **Python 3.12+**
- **Node.js 18+**
- **AWS credentials** with access to SageMaker endpoints and Bedrock
- **SageMaker endpoints** deployed for Deepgram Flux (STT) and Aura-2 (TTS)
- **Bedrock model access** enabled for Claude Haiku in your AWS region

## Quick Start

### 1. Clone the repo

```bash
git clone <repo-url>
cd Patient-Connect
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your AWS credentials and endpoint names:

```env
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
SAGEMAKER_ENDPOINT_NAME=your-stt-flux-endpoint
SAGEMAKER_ENDPOINT_NAME_TTS=your-tts-endpoint
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
```

### 3. Start the server

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The server runs on **http://localhost:8000**.

### 4. Start the client

In a new terminal:

```bash
cd client
npm install
npm run dev
```

### 5. Open the app

Go to **http://localhost:5173**, select a patient, click **Connect**, and start talking.

## How It Works

1. The agent greets the patient by name (TTS, no LLM round-trip)
2. Flux STT transcribes the patient's speech with built-in turn detection
3. On end-of-turn, the transcript is sent to Bedrock Claude
4. Claude generates a contextual response based on the patient's record
5. Aura-2 TTS synthesizes the response and streams audio back to the browser
6. The conversation continues until the patient or agent ends the call

## Project Structure

```
.env.example                        # Environment config template (copy to .env)
patient_promotions_dataset.jsonl     # Sample patient records

server/
  main.py           # WebSocket server — STT, TTS, LLM orchestration
  config.py         # Environment-based configuration
  call_prompts.py   # System prompt and greeting templates
  dataset.py        # JSONL patient data loader
  requirements.txt  # Python dependencies

client/
  src/
    App.tsx                         # Main app layout
    hooks/useVoiceSession.ts        # WebSocket + Web Audio mic/speaker
    hooks/useEligibleRecords.ts     # Patient data fetching
    components/ConversationPanel.tsx # Live conversation display
    components/DataTable.tsx         # Patient record table
    components/DataBrowser.tsx       # Sidebar navigation
```

