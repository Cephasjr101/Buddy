# Trust & Compliance Audit - AgentHub MVP

Date: 2026-11-11. Scope: this codebase as shipped.

## Third-party SDKs & external calls (full inventory)
| Party | Purpose | When active | Data sent |
|---|---|---|---|
| OpenAI (optional) | Intent parsing, replies, post drafts, Whisper/TTS fallback | Only if OPENAI_API_KEY set | Message text, audio (transcription) |
| VoiceStudio (local, AGPL) | STT / TTS / voice cloning | Only if VOICESTUDIO_DIR set | Nothing leaves server |
| Twilio (optional) | Outbound calls | Only if TWILIO_* set | Call audio/script, callee number |
| Meta Graph API (optional) | WhatsApp alerts, FB/IG posting | Only if tokens set | Message text you command |
| Google Places API (optional) | Lead search | Only if GOOGLE_PLACES_KEY set | Search query + city |
| SerpAPI (optional) | Web lead search | Only if SERPAPI_KEY set | Search query |
| Your SMTP (optional) | Email sending | Only if SMTP_* set | Email content |

**Zero analytics SDKs, zero advertising trackers, zero cookies for tracking.**
The only cookie is the strictly-necessary session (HttpOnly, Secure, SameSite=Strict).

## Checklist
- Form consents: register requires explicit age (16+) + Terms/Privacy checkboxes, unchecked by default
- Data minimization: only email + password + name required; phone optional; nothing else collected
- Dark patterns: none - consent banner has equal Accept/Decline; decline keeps full service (session cookie still required to function)
- Hidden fees: none - service is free in beta; no payment flows exist in this app
- Fake reviews: no review/rating features ship in this codebase
- Unsupported claims: marketing copy describes shipped features only; AI output disclaimer page included
- Alt text: all content images carry descriptive alt; decorative icons are empty-alt
- Color contrast: text raised to >= 4.5:1 (WCAG AA); focus rings 3:1+
- Keyboard navigation: all controls are native buttons/inputs/links; :focus-visible ring added
- Age consent: 16+ affirmation required at registration + Terms statement
- Unsubscribe: every agent-sent email carries an opt-out footer + account-settings link
- Licensed images: this repo ships no images; user-supplied product/voice data is their responsibility - use licensed media only
- Data deletion: self-serve account deletion (account page) wipes users/agents/messages/tasks/posts/leads
- Data access: "Download all my data (JSON)" on the account page (/api/export)
