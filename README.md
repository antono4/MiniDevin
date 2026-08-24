# 🐚 MiniDevin — Code Less, Make More

Versi mini dari [OpenDevin/OpenHands](https://github.com/All-Hands-AI/OpenHands): agen AI software engineer otonom dengan antarmuka web chat. Agen dapat menulis file, menjalankan perintah bash di sandbox, membaca hasilnya, dan memverifikasi pekerjaannya sendiri — persis konsep agent loop OpenDevin.

## Arsitektur

```
Browser (chat UI) ──WebSocket──> FastAPI server ──> Agent loop ──> LLM (OpenAI-compatible API)
                                       │
                                       └── Tools: run_bash · write_file · read_file · finish
```

- `minidevin/agent.py` — agent loop + definisi & eksekusi tools (sandboxed di `sandbox/`)
- `minidevin/server.py` — FastAPI: WebSocket `/ws`, REST `/api/settings` & `/api/status`
- `minidevin/static/index.html` — UI chat (dark theme ala OpenDevin)
- `sandbox/` — direktori kerja agen (path traversal keluar sandbox diblokir)

## Menjalankan

```bash
pip install -r requirements.txt
python3 -m uvicorn minidevin.server:app --host 0.0.0.0 --port 12000
```

Buka `http://localhost:12000`, klik **⚙️ Settings**, lalu masukkan:
- **Model** — mis. `gpt-4o-mini`, `gpt-4o`, atau model lain
- **API Key** — key OpenAI / OpenRouter / provider OpenAI-compatible lain
- **Base URL** — opsional, mis. `https://openrouter.ai/api/v1`

Konfigurasi juga bisa lewat environment variable: `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`.

## Cara kerja agent loop

1. Pesan user + riwayat dikirim ke LLM beserta skema tools (function calling).
2. Jika LLM memanggil tool → server mengeksekusinya di sandbox → hasil (observasi) dikirim balik ke LLM.
3. Berulang hingga LLM memanggil `finish` atau mencapai batas 30 langkah.
4. Setiap langkah (pemikiran, aksi, observasi) distreaming ke UI secara real-time.

## Batasan vs OpenDevin asli

MiniDevin adalah versi edukasi ~300 baris: belum ada Docker sandbox per-sesi, multi-agent, browsing, atau persistent session. Untuk versi penuh, gunakan [OpenHands](https://github.com/All-Hands-AI/OpenHands).
