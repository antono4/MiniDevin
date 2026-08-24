# 🐚 MiniDevin — Code Less, Make More

Versi mini dari [OpenDevin/OpenHands](https://github.com/All-Hands-AI/OpenHands): agen AI software engineer otonom dengan antarmuka web lengkap. Agen menulis file, menjalankan bash di sandbox, membaca hasilnya, dan memverifikasi pekerjaannya sendiri.

## Fitur v2

- **Split view UI** — chat di kiri; panel kanan berisi 📁 Files (explorer sandbox), 💻 Terminal (log semua perintah agen), dan 📄 Viewer (klik file untuk melihat isi)
- **6 tools agen** — `run_bash`, `write_file`, `edit_file` (string replace presisi), `read_file`, `list_files` (tree), `finish`
- **Riwayat percakapan tersimpan** — sesi persisten di `.minidevin/sessions/`, bisa dibuka kembali lewat menu 🕘 Riwayat
- **Tombol ⏹ Stop** — hentikan agen di tengah jalan (cancellable agent loop)
- **Markdown rendering** — jawaban agen dirender dengan `marked` + `DOMPurify`
- **Token usage** — jumlah token ditampilkan setelah tiap run
- **Konfigurasi persisten** — settings disimpan di `.minidevin/config.json` (env: `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`)
- **Safety guard** — blokir perintah bash berbahaya + path traversal keluar sandbox ditolak

## Arsitektur

```
Browser (split-view UI) ──WebSocket──> FastAPI ──> Agent loop ──> LLM (OpenAI-compatible)
                              │
                              ├── REST: /api/files · /api/file · /api/sessions · /api/settings
                              └── Tools: run_bash · write_file · edit_file · read_file · list_files · finish
```

## Menjalankan

```bash
pip install -r requirements.txt
python3 -m uvicorn minidevin.server:app --host 0.0.0.0 --port 12000
```

Buka `http://localhost:12000` → ⚙️ Settings → masukkan Model + API Key (+ Base URL opsional untuk OpenRouter/Ollama/lokal).

## Cara kerja agent loop

1. Pesan user + riwayat dikirim ke LLM beserta skema tools (function calling).
2. Jika LLM memanggil tool → server mengeksekusinya di sandbox → observasi dikirim balik ke LLM.
3. Berulang hingga `finish` atau batas 40 langkah; setiap langkah distreaming ke UI.
4. Hasil run (events + history) disimpan sebagai sesi yang bisa dimuat ulang.

## Roadmap (vs OpenDevin penuh)

Belum ada: Docker sandbox per-sesi, multi-agent delegation, browser tool, dan integrasi git. Untuk versi penuh, gunakan [OpenHands](https://github.com/All-Hands-AI/OpenHands).
