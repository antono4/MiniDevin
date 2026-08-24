# 🐚 MiniDevin — Code Less, Make More

Versi mini dari [OpenDevin/OpenHands](https://github.com/All-Hands-AI/OpenHands): agen AI software engineer otonom dengan antarmuka web lengkap. Agen menulis file, menjalankan bash di sandbox, riset web, dan memverifikasi pekerjaannya sendiri.

## Fitur

**Agen & Tools**
- 7 tools: `run_bash` · `write_file` · `edit_file` · `read_file` · `list_files` · `web_fetch` · `finish`
- **Streaming real-time** — pemikiran LLM mengalir token-per-token ke chat
- **Mode 🧠 Rencana** — planner menyusun rencana, agen coder mengeksekusi
- Agent loop cancellable (⏹ Stop), batas 40 langkah, token usage
- Safety guard: perintah bash berbahaya diblokir, path traversal ditolak

**Multi-workspace** *(v5)*
- Dropdown 📂 di header: pisahkan proyek ke workspace terisolasi di `sandboxes/<nama>/`
- Setiap workspace punya repo git, file explorer, dan riwayat sesi sendiri
- Nama workspace disanitasi (huruf/angka/`._-`), auto-create saat dipakai

**Antarmuka (split view)**
- Chat dengan Markdown + streaming, blok aksi/observasi collapsible
- 🎤 Voice input (Web Speech API, Bahasa Indonesia)
- ⚡ Template prompt siap pakai (REST API, analisis CSV, riset web, debug)
- 📁 Files + ⬆ Upload · 💻 Terminal · 📄 Viewer/Editor mini (💾 Simpan, ⬇ Unduh) · 🌿 Git (klik commit = diff)
- 📤 **Ekspor percakapan ke Markdown** (`GET /api/export?id=...`)

**Persistensi**
- Sesi di `.minidevin/sessions/` (dengan field workspace) · konfigurasi di `.minidevin/config.json`
- Env: `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`, `MINIDEVIN_WORKSPACES`

## API

| Endpoint | Deskripsi |
|---|---|
| `GET /api/workspaces` | Daftar workspace |
| `GET /api/files?ws=` | File tree workspace |
| `GET/POST /api/file` | Baca / simpan file |
| `POST /api/upload?ws=` | Upload file (maks 20MB) |
| `GET /api/download` | Unduh file |
| `GET /api/git/log?ws=` · `GET /api/git/diff?ws=&sha=` | Riwayat & diff git |
| `GET /api/sessions` · `GET /api/export?id=` | Sesi & ekspor Markdown |
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
