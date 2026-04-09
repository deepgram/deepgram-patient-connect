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
| **STT** | Deepgram Flux on SageMaker (`deepgram-sagemaker` 0.2.1) |
| **TTS** | Deepgram Aura-2 on SageMaker (`deepgram-sagemaker` 0.2.1) |
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

### 1. Configure environment

```bash
cp server/.env.example server/.env
# Edit server/.env with your AWS credentials and SageMaker endpoint names
```

Or create `server/.env`:

```env
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
SAGEMAKER_ENDPOINT_NAME=your-stt-flux-endpoint
SAGEMAKER_ENDPOINT_NAME_TTS=your-tts-endpoint
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
```

### 2. Start the server

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### 3. Start the client

```bash
cd client
npm install
npm run dev
```

### 4. Open the app

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

patient_promotions_dataset.jsonl    # Sample patient records
```

## Key Technical Details

- **No framework overhead** — no Pipecat, no uvicorn, no FastAPI. The server is ~300 lines of Python using `websockets` and `asyncio.run()` directly.
- **WAV header trick** — `deepgram-sagemaker` 0.2.1's v2/listen requires a WAV header prepended to the audio stream instead of passing `encoding`/`sample_rate` parameters.
- **Factory swapping** — the Deepgram SDK only supports one transport factory per process. STT and TTS swap factories via `restore_transport()` between connections.
- **Browser audio** — mic capture uses `ScriptProcessorNode` with manual downsampling from the device's native rate to 16kHz PCM16.

## License

MIT
