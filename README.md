## Phase 1: Content Generation
```
LLM generates script/prompt
    ↓
Format prompt for video generation
    ↓
Send to ComfyUI API
```

**Tools:**
- Local LLM (Ollama - free) or Claude/ChatGPT API
- Python script to generate prompts based on your niche

---

## Phase 2: Video Generation (ComfyUI)
```
ComfyUI receives prompt via API
    ↓
Generates video (5-10 min per video)
    ↓
Saves to output folder
```

**Setup:**
- ComfyUI with Stable Video Diffusion workflow
- Enable API mode (--listen flag)
- Python script sends requests to ComfyUI API
- Monitor output folder for completed videos

**Key Detail:** ComfyUI has an API you can call from Python!

---

## Phase 3: Post-Processing
```
Raw AI video generated
    ↓
Add TTS voiceover (if needed) - Will have to see what works best under limits of stable diffusion
    ↓
Add animated captions with MoviePy
    ↓
Add music/sound effects (optional)
    ↓
Format for YouTube Shorts (9:16 aspect ratio)
```

**Tools:**
- MoviePy for editing
- Edge TTS or gTTS for voiceover
- FFmpeg for final encoding

---

## Phase 4: YouTube Upload
```
Finished video ready
    ↓
Generate title/description with LLM
    ↓
Upload via YouTube API
    ↓
Schedule or post immediately
```

**Tools:**
- YouTube Data API v3
- Python google-api-client library
- OAuth2 authentication (one-time setup)