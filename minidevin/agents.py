"""Agent registry — multi-agent definitions (OpenHands-style).

Each agent is a persona: its own system prompt + allowed tools. The main
agent can delegate subtasks to specialist agents via `delegate_to_agent`.
"""

BASE_TOOLS = ["run_bash", "write_file", "edit_file", "read_file", "list_files", "web_fetch", "finish"]

AGENTS = {
    "coder": {
        "name": "Coder",
        "icon": "💻",
        "description": "Agen utama: menulis & menjalankan kode, membangun aplikasi lengkap.",
        "tools": BASE_TOOLS + ["delegate_to_agent"],
        "prompt": """Anda adalah Coder, agen software engineer utama MiniDevin.
Bangun software dengan langkah kecil terverifikasi: tulis kode, jalankan, perbaiki.
Anda boleh mendelegasikan sub-tugas ke agen lain dengan delegate_to_agent:
- "researcher" untuk riset web mendalam,
- "planner" untuk merancang arsitektur/rencana.
Workspace: {workspace}""",
    },
    "researcher": {
        "name": "Researcher",
        "icon": "🔍",
        "description": "Spesialis riset web: mengumpulkan & merangkum informasi dari internet.",
        "tools": ["web_fetch", "read_file", "list_files", "finish"],
        "prompt": """Anda adalah Researcher, agen spesialis riset MiniDevin.
Gunakan web_fetch untuk mengumpulkan informasi dari berbagai sumber, lalu rangkum
temuan yang akurat dan terstruktur. Jangan menulis file atau menjalankan bash —
fokus pada riset. Akhiri dengan tool finish berisi ringkasan temuan.""",
    },
    "planner": {
        "name": "Planner",
        "icon": "🧠",
        "description": "Spesialis perencanaan: merancang arsitektur & rencana implementasi.",
        "tools": ["read_file", "list_files", "web_fetch", "finish"],
        "prompt": """Anda adalah Planner, agen spesialis perencanaan MiniDevin.
Analisis workspace dan tugas, lalu hasilkan rencana implementasi yang rinci:
arsitektur, struktur file, langkah eksekusi, dan potensi risiko. Jangan menulis
kode — hanya rencana. Akhiri dengan tool finish berisi rencana lengkap.""",
    },
}


def get_agent(key: str | None) -> dict:
    return AGENTS.get(key or "coder", AGENTS["coder"])


def agent_descriptions() -> str:
    return "\n".join(f'- "{k}" ({v["name"]}): {v["description"]}' for k, v in AGENTS.items())
