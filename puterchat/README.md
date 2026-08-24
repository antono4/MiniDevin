# 🐱 PuterChat — AI Chat dengan Puter.js

Aplikasi chat AI **serverless** — tanpa backend, tanpa API key. Cukup satu file HTML + Puter.js.

## Fitur

- 🤖 **500+ model AI** (GPT, Claude, Gemini, DeepSeek, Grok, dll) via `puter.ai.chat()` — pilih dari dropdown
- ⚡ **Streaming** token-per-token (bisa dimatikan)
- 🎨 **Text-to-image** — ketik `/gambar <deskripsi>` untuk membuat gambar via `puter.ai.txt2img()`
- 🔑 **Auth Puter** — login akun Puter; riwayat chat tersimpan di cloud (`puter.kv`)
- 💾 Riwayat percakapan persisten (KV store saat login, localStorage saat anonim)
- 🌓 Tema terang/gelap · 📋 tombol salin di code block · Markdown rendering
- Model User-Pays Puter: pengguna memakai kuota akun Puter mereka sendiri

## Menjalankan

Puter.js mengharuskan penyajian lewat HTTP (bukan `file://`):

```bash
# lokal
python3 -m http.server 8080
# buka http://localhost:8080
```

Atau langsung buka versi hosted: **https://antono4.github.io/PuterChat/**

## Cara kerja

Satu `<script src="https://js.puter.com/v2/"></script>` — selesai. Semua kemampuan (AI, auth, KV) disediakan Puter.js langsung dari browser. Lihat dokumentasi: https://docs.puter.com
