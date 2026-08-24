# 🐚 MiniDevin — Code Less, Make More

Versi mini dari [OpenDevin/OpenHands](https://github.com/All-Hands-AI/OpenHands): agen AI software engineer otonom dengan antarmuka web lengkap. Agen menulis file, menjalankan bash di sandbox, riset web, dan memverifikasi pekerjaannya sendiri.

## Fitur

**Agen & Tools**
- 7 tools: `run_bash` · `write_file` · `edit_file` (string replace presisi) · `read_file` · `list_files` (tree) · `web_fetch` (riset internet) · `finish`
- **Streaming real-time** — pemikiran LLM mengalir token-per-token ke chat (fallback otomatis untuk provider tanpa `stream_options`)
- **Mode 🧠 Rencana** — planner menyusun rencana dulu, lalu agen coder mengeksekusinya
- Agent loop cancellable (⏹ Stop), batas 40 langkah, token usage ditampilkan
- Safety guard: perintah bash berbahaya diblokir, path traversal keluar sandbox ditolak

**Antarmuka (split view)**
- Chat dengan Markdown rendering, blok aksi/observasi collapsible
- 🎤 **Voice input** (Web Speech API, Bahasa Indonesia)
- 📁 **Files** — file explorer + ⬆ Upload (maks 20MB)
- 💻 **Terminal** — log semua perintah bash agen
- 📄 **Viewer = Editor mini** — edit file langsung, 💾 Simpan (POST /api/file), ⬇ Unduh
- 🌿 **Git** — snapshot otomatis tiap tugas selesai; klik commit untuk melihat diff

**Persistensi**
- Riwayat percakapan di `.minidevin/sessions/` (menu 🕘 Riwayat)
- Konfigurasi LLM di `.minidevin/config.json`
- Env: `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`

## Arsitektur

```
Browser ──WebSocket──> FastAPI ──> [Planner?] ──> Agent loop ──> LLM (OpenAI-compatible, streaming)
                          │                            │
                          ├─ /api/files · /api/file    ├─ tools: bash · file · web_fetch · finish
                          ├─ /api/upload · /api/download └─ git snapshot tiap tugas selesai
                          └─ /api/git/log · /api/git/diff · /api/sessions · /api/settings
```

## Menjalankan

```bash
pip install -r requirements.txt
python3 -m uvicorn minidevin.server:app --host 0.0.0.0 --port 12000
```

Buka `http://localhost:12000` → ⚙️ Settings → isi Model + API Key (+ Base URL opsional untuk OpenRouter/Ollama/lokal).

## Roadmap

Belum ada: Docker sandbox per-sesi (Docker tidak tersedia di environment ini), multi-agent penuh, browser interaktif. Untuk versi produksi, gunakan [OpenHands](https://github.com/All-Hands-AI/OpenHands).
