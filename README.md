# 🐚 MiniDevin — Code Less, Make More

Versi mini dari [OpenDevin/OpenHands](https://github.com/All-Hands-AI/OpenHands): agen AI software engineer otonom dengan antarmuka web lengkap. Agen menulis file, menjalankan bash di sandbox, riset web, dan memverifikasi pekerjaannya sendiri.

## Fitur

**Agen & Tools**
- 7 tools: `run_bash` · `write_file` · `edit_file` (string replace presisi) · `read_file` · `list_files` (tree) · `web_fetch` (riset internet) · `finish`
- **Mode 🧠 Rencana** — planner menyusun rencana dulu, lalu agen coder mengeksekusinya (toggle di input bar)
- Agent loop cancellable (tombol ⏹ Stop), batas 40 langkah, token usage ditampilkan
- Safety guard: perintah bash berbahaya diblokir, path traversal keluar sandbox ditolak

**Antarmuka (split view)**
- Chat dengan Markdown rendering (marked + DOMPurify), blok aksi/observasi collapsible
- 📁 **Files** — file explorer sandbox + tombol ⬆ Upload (maks 20MB)
- 💻 **Terminal** — log semua perintah bash agen
- 📄 **Viewer** — klik file untuk melihat isi
- 🌿 **Git** — snapshot otomatis setiap tugas selesai; log commit tampil di sini

**Persistensi**
- Riwayat percakapan tersimpan di `.minidevin/sessions/` (menu 🕘 Riwayat)
- Konfigurasi LLM tersimpan di `.minidevin/config.json`
- Env: `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`

## Arsitektur

```
Browser ──WebSocket──> FastAPI ──> [Planner?] ──> Agent loop ──> LLM (OpenAI-compatible)
                          │                            │
                          ├─ REST: /api/files          ├─ tools: bash · file · web_fetch · finish
                          ├─ /api/file · /api/upload   └─ git snapshot tiap tugas selesai
                          └─ /api/git/log · /api/sessions · /api/settings
```

## Menjalankan

```bash
pip install -r requirements.txt
python3 -m uvicorn minidevin.server:app --host 0.0.0.0 --port 12000
```

Buka `http://localhost:12000` → ⚙️ Settings → isi Model + API Key (+ Base URL opsional untuk OpenRouter/Ollama/lokal).

## Roadmap

Belum ada: Docker sandbox per-sesi, multi-agent penuh, browser interaktif. Untuk versi produksi, gunakan [OpenHands](https://github.com/All-Hands-AI/OpenHands).
