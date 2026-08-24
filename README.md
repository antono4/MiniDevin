# 🐚 MiniDevin — Code Less, Make More

Versi mini dari [OpenDevin/OpenHands](https://github.com/All-Hands-AI/OpenHands): agen AI software engineer otonom dengan antarmuka web lengkap. Agen menulis file, menjalankan bash di sandbox, riset web, dan memverifikasi pekerjaannya sendiri.

## Fitur

**Agen & Tools**
- 8 tools: `run_bash` · `write_file` · `edit_file` · `read_file` · `list_files` · `web_fetch` · `set_api_key` · `finish`
- **Streaming real-time** — pemikiran LLM mengalir token-per-token ke chat
- **Mode 🧠 Rencana** — planner menyusun rencana, agen coder mengeksekusi
- **Slash commands** — `/plan`, `/web <topik>`, `/run <perintah>`, `/reset` dengan autocomplete (ketik `/`)
- Agent loop cancellable (⏹ Stop), batas 40 langkah, token usage
- Safety guard: perintah bash berbahaya diblokir, path traversal ditolak

**Multi-workspace**
- Dropdown 📂 di header: pisahkan proyek ke workspace terisolasi di `sandboxes/<nama>/`
- Setiap workspace punya repo git, file explorer, dan riwayat sesi sendiri

**Antarmuka (split view)**
- Chat dengan Markdown + streaming, blok aksi/observasi collapsible, tombol 📋 salin di code block
- 🌓 **Tema terang/gelap** (CSS variables, tersimpan di localStorage)
- 🎤 Voice input + 🔊 **TTS** jawaban akhir agen (Web Speech API, Bahasa Indonesia)
- ⚡ Template prompt siap pakai · 🔍 **Pencarian & penghapusan riwayat** di modal 🕘 Riwayat
- 📁 Files + ⬆ Upload · 💻 Terminal · 📄 Editor mini (💾 Simpan, ⬇ Unduh) · 🌿 Git (klik commit = diff)
- 📤 Ekspor percakapan ke Markdown

**Persistensi**
- Sesi di `.minidevin/sessions/` · konfigurasi di `.minidevin/config.json`
- Env: `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`, `MINIDEVIN_WORKSPACES`

## API

| Endpoint | Deskripsi |
|---|---|
| `GET /api/workspaces` | Daftar workspace |
| `GET /api/files?ws=` | File tree workspace |
| `GET/POST /api/file` | Baca / simpan file |
| `POST /api/upload?ws=` · `GET /api/download` | Upload / unduh file |
| `GET /api/git/log?ws=` · `GET /api/git/diff?ws=&sha=` | Riwayat & diff git |
| `GET /api/sessions` · `GET /api/sessions/search?q=` · `DELETE /api/sessions/{id}` | Kelola sesi |
| `GET /api/export?id=` | Ekspor Markdown |
| `GET/POST /api/settings` · `GET /api/status` | Konfigurasi LLM |
| `WS /ws` | Chat agent loop (init · new_session · chat · stop) |

## Menjalankan

```bash
pip install -r requirements.txt
python3 -m uvicorn minidevin.server:app --host 0.0.0.0 --port 12000
```

Buka `http://localhost:12000` → ⚙️ Settings → isi Model + API Key (+ Base URL opsional untuk OpenRouter/Ollama).

## Roadmap

Belum ada: Docker sandbox per-sesi (Docker tidak tersedia di environment ini), multi-agent penuh, browser interaktif. Untuk versi produksi, gunakan [OpenHands](https://github.com/All-Hands-AI/OpenHands).
