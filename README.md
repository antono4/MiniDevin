# 🐚 MiniDevin — Code Less, Make More

Miniatur [OpenHands](https://github.com/OpenHands/OpenHands) dengan arsitektur yang setara: agen AI software engineer otonom dengan antarmuka web lengkap.

## Arsitektur (OpenHands-parity)

```
Browser (split-view UI) ──WebSocket──> FastAPI server
                                            │
                                    Conversation loop (agent.py)
                                            │
                ┌───────────────────────────┼───────────────────────────┐
                ▼                           ▼                           ▼
        EventStream (events.py)      Runtime (runtime.py)         Agent registry (agents.py)
        append-only JSONL            LocalRuntime: bash,          💻 Coder · 🔍 Researcher
        per-sesi, replayable         file ops, web_fetch          · 🧠 Planner + delegate_to_agent
                                            │
                                    LLM (OpenAI-compatible, streaming)
```

Prinsip inti (sama seperti OpenHands): **agen adalah fungsi dari riwayat event ke aksi berikutnya** — setiap aksi menghasilkan observasi yang di-append ke event stream, loop berjalan hingga `finish`.

## Fitur

**Agen & Multi-agent**
- 3 persona: 💻 **Coder** (tools lengkap + delegasi), 🔍 **Researcher** (web_fetch saja), 🧠 **Planner** (analisis + rencana)
- **`delegate_to_agent`** — agen utama mendelegasikan sub-tugas ke spesialis (batas kedalaman 2), laporan sub-agen kembali sebagai observasi
- 9 tools: `run_bash` · `write_file` · `edit_file` · `read_file` · `list_files` · `web_fetch` · `set_api_key` · `delegate_to_agent` · `finish`
- **Streaming real-time** · agent state machine (running/awaiting_confirmation/finished/stopped/error)
- **🛡️ Mode konfirmasi** (`/confirm`) — setiap aksi bash/tulis/edit meminta persetujuan user (security gate ala OpenHands)
- Slash commands: `/plan` `/web` `/run` `/reset` `/confirm` dengan autocomplete

**Event stream**
- Append-only JSONL per sesi (`.minidevin/sessions/<id>.jsonl`) — replayable, dengan `cause` linking aksi→observasi
- API: `GET /api/events?id=`

**Antarmuka**
- Tema 🌓 · voice input 🎤 · TTS 🔊 · template prompt · ekspor Markdown 📤
- 📁 Files + upload · 💻 Terminal · 📄 Editor mini · 🌿 Git (klik commit = diff) · 🔍 search/hapus riwayat
- Badge status agen real-time di header · indikator delegasi 🔀 · dialog konfirmasi inline

## API

| Endpoint | Deskripsi |
|---|---|
| `GET /api/status` | Status + daftar agen |
| `GET /api/workspaces` · `GET /api/files?ws=` | Multi-workspace |
| `GET/POST /api/file` · `POST /api/upload` · `GET /api/download` | File ops |
| `GET /api/git/log?ws=` · `GET /api/git/diff?ws=&sha=` | Git |
| `GET /api/sessions` · `GET /api/sessions/search?q=` · `DELETE /api/sessions/{id}` | Sesi |
| `GET /api/events?id=` | Event stream (JSONL) |
| `GET /api/export?id=` | Ekspor Markdown |
| `GET/POST /api/settings` | Konfigurasi LLM |
| `WS /ws` | init · new_session · chat · stop · confirm · set_confirmation |

## Menjalankan

```bash
pip install -r requirements.txt
python3 -m uvicorn minidevin.server:app --host 0.0.0.0 --port 12000
```

Buka `http://localhost:12000` → ⚙️ Settings → isi Model + API Key (+ Base URL untuk OpenRouter/Ollama).

## Frontend di GitHub Pages

`index.html` di root repo adalah salinan deployment dari `minidevin/static/index.html`, disajikan via GitHub Pages di **https://antono4.github.io/MiniDevin/**. Karena Pages hanya hosting statis, frontend meminta **Backend URL** (alamat server `uvicorn` yang berjalan) saat pertama dibuka — tersimpan di localStorage. Server sudah mengaktifkan CORS (`allow_origins=["*"]`) agar REST API bisa diakses lintas origin; WebSocket tidak dibatasi origin.

Saat mengubah `minidevin/static/index.html`, sinkronkan salinannya: `cp minidevin/static/index.html index.html`.

## Perbandingan dengan OpenHands

| Aspek | OpenHands | MiniDevin |
|---|---|---|
| Event stream append-only | ✅ | ✅ (JSONL per sesi) |
| Runtime eksekusi | ✅ (Docker/lokal/remote) | ✅ (lokal; Docker tak tersedia di env ini) |
| Multi-agent + delegasi | ✅ | ✅ (3 persona, kedalaman 2) |
| Confirmation mode | ✅ | ✅ |
| Agent state machine | ✅ | ✅ |
| Streaming LLM | ✅ | ✅ |
| Sandbox Docker | ✅ | ❌ (roadmap) |
| Browser interaktif | ✅ | ❌ (web_fetch saja) |
| Plugin/microagent | ✅ | ❌ (roadmap) |
