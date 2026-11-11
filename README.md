# AgentHub MVP

Named AI agents (personal or business) driven by voice notes and text:
calls, appointments, reminders, music, email, and daily marketing - with
local voice cloning/TTS/STT powered by VoiceStudio.

## What works out of the box (no keys)
- Accounts: register/login/change-password/delete-account
- Create named agents (personal or business), delete agents
- Chat by text: intents parsed by built-in parser
  - "remind me to call mum at 6pm" -> scheduled reminder (fires in-app)
  - "schedule a call with Kofi tomorrow at 3pm" -> call task (Twilio when set)
  - "play Burna Boy" -> music link
  - "send email to x@y.com saying hello" -> SMTP send (or draft)
  - "create a marketing post about new arrivals" -> drafted post
- Business agents auto-generate marketing posts 3-5x/day (queue visible; publish needs Meta tokens)
- Records dashboard (tasks/appointments/reminders/call log)
- Marketing drafts + one-click publish (Meta Graph API)
- Skills dashboard showing READY / NOT CONFIGURED per integration
- Terms & Privacy pages, favicon, responsive dark UI

## Voice (install VoiceStudio skill)
1. Provision a GPU-capable server (VoiceStudio needs CUDA for best results; CPU works slowly)
2. git clone https://github.com/debpalash/VoiceStudio && follow its README (pip install -e .)
3. Point AgentHub at it:  VOICESTUDIO_DIR=/opt/VoiceStudio
Then: agent page -> "Clone voice" (upload 30-60s sample) -> your agent speaks
with that cloned voice, and voice notes transcribe locally in 646 languages.
Without VoiceStudio, set OPENAI_API_KEY for Whisper/TTS fallback - else text-only.

## Deploy (Fly.io)
    fly launch --name agenthub --region iad --no-deploy
    fly volumes create agenthubdata --region iad --size 1
    fly secrets set SHOP_SECRET="$(openssl rand -hex 32)" BASE_URL="https://agenthub.fly.dev" \
        ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=strongpass
    fly deploy
Optional secrets: OPENAI_API_KEY, TWILIO_SID/TOKEN/FROM, WHATSAPP_TOKEN/PHONE_ID,
FACEBOOK_PAGE_TOKEN, INSTAGRAM_BUSINESS_ID, SMTP_HOST/USER/PASS/FROM

## VoiceStudio note
VoiceStudio is AGPL-3.0 licensed open source (github.com/debpalash/VoiceStudio).
Because of the AGPL, if you MODIFY VoiceStudio and offer it as a networked
service, you must publish your modifications. Using it unmodified as an
internal engine is fine.
