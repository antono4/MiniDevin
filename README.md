<div align="center">
  <img src="minidevin.jpg" alt="MiniDevin" width="480">

  # 🐚 MiniDevin — Code Less, Make More

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
  [![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://antono4.github.io/MiniDevin/)

  Aplikasi web **serverless** — AI software engineer langsung dari browser, tanpa backend dan tanpa API key. Bertenaga [Puter.js](https://docs.puter.com) dengan 500+ model (GPT, Claude, Gemini, DeepSeek, Grok, dll).
</div>

## ✨ Fitur Frontend (Serverless)

- 🤖 **500+ model AI** via `puter.ai.chat()` — pilih dari dropdown (`puter.ai.listModels()`)
- ⚡ **Streaming real-time** (bisa dimatikan) dengan tombol salin kode
- 🎨 **Text-to-image** — ketik `/gambar <deskripsi>` (`puter.ai.txt2img()`)
- 🔑 **Auth Puter** — login akun Puter; riwayat chat tersimpan di cloud (`puter.kv`, key `minidevin_convos`), fallback ke localStorage
- 🌓 Tema gelap/terang · 📱 responsif penuh (drawer mobile, safe-area iOS)
- 🧠 System prompt bawaan: MiniDevin bertindak sebagai asisten software engineer
- 💾 Tanpa server — satu file HTML statis; model User-Pays Puter (pengguna memakai kuota akun Puter mereka)

## 🚀 Menjalankan Frontend

Lewat HTTP (Puter.js menolak `file://`):

```bash
python3 -m http.server 12000
# buka http://localhost:12000
```

Atau langsung versi hosted: **https://antono4.github.io/MiniDevin/**

`index.html` di root repo dan `app/index.html` adalah salinan deployment dari `minidevin/static/index.html`. Saat mengubah frontend, sinkronkan keduanya:

```bash
cp minidevin/static/index.html index.html
cp minidevin/static/index.html app/index.html
```

## 🖥️ Backend Agent (Opsional, Self-Hosted)

Paket `minidevin` (FastAPI + OpenAI-compatible LLM) berisi mode agent penuh ala [OpenHands](https://github.com/OpenHands/OpenHands):

- 📜 Event stream append-only per sesi (`.minidevin/sessions/<id>.jsonl`)
- ⚙️ Runtime eksekusi bash, file ops, dan web fetch
- 👥 Multi-agent (💻 Coder · 🔍 Researcher · 🧠 Planner) dengan delegasi
- 🛡️ Mode konfirmasi & 📸 git snapshot otomatis
- 🔌 REST & WebSocket API

```bash
pip install -r requirements.txt
python3 -m uvicorn minidevin.server:app --host 0.0.0.0 --port 12000
```

> **Catatan:** frontend GitHub Pages kini sepenuhnya serverless (Puter.js), sehingga backend tidak lagi diperlukan untuk pemakaian umum. Backend disediakan bagi yang ingin menjalankan agent loop penuh secara lokal.

## 📂 Struktur Repo

| Path | Isi |
|---|---|
| `index.html` | Frontend serverless (GitHub Pages) |
| `app/index.html` | Salinan frontend (`/app/`) |
| `minidevin/` | Backend agent Python + `static/index.html` (sumber frontend) |
| `puterchat/` | Aplikasi PuterChat asli (dipertahankan) |
| `minidevin.png` / `minidevin.jpg` | Logo |
| `favicon.png` | Ikon situs |
| `requirements.txt` | Dependensi backend Python |
| `LICENSE` | MIT License |

## 📄 Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE) — bebas digunakan, dimodifikasi, dan didistribusikan.

---

_Model User-Pays Puter: pengguna memakai kuota akun Puter mereka sendiri. Dokumentasi: https://docs.puter.com_
