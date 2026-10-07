#!/usr/bin/env python3
"""commit-ai: genera mensajes de commit (Conventional Commits) con IA.

Lee tus cambios de git, se los pide a un modelo (Gemini, OpenAI o Anthropic)
y te propone un mensaje. No necesita librerías externas, solo Python 3.8+.

Uso rápido:
    python commit_ai.py                 # sugiere un mensaje para los cambios en staging
    python commit_ai.py --commit        # sugiere y hace el commit (pide confirmación)
    python commit_ai.py --provider openai
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Configuración por proveedor (puedes cambiar el modelo con COMMIT_AI_MODEL)
# ---------------------------------------------------------------------------
PROVIDERS = {
    "gemini": {"env_key": "GEMINI_API_KEY", "default_model": "gemini-2.5-flash"},
    "openai": {"env_key": "OPENAI_API_KEY", "default_model": "gpt-4o-mini"},
    "anthropic": {"env_key": "ANTHROPIC_API_KEY", "default_model": "claude-haiku-4-5"},
}

MAX_DIFF_CHARS = 12000  # límite para no enviar diffs enormes
TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = (
    "Eres un asistente que escribe mensajes de commit siguiendo el estándar "
    "Conventional Commits (feat, fix, docs, style, refactor, perf, test, build, ci, chore). "
    "Reglas: primera línea de máximo 72 caracteres con formato 'tipo(ámbito opcional): descripción' "
    "en imperativo y minúsculas; si hace falta, deja una línea en blanco y un cuerpo breve "
    "explicando el porqué. Responde SOLO con el mensaje de commit, sin comillas, sin bloques "
    "de código y sin explicaciones."
)

# Patrones simples para detectar secretos en las líneas añadidas del diff.
SECRET_PATTERNS = [
    ("Clave de OpenAI/Anthropic", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("Clave de Google", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Token de GitHub", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("Clave de AWS", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Clave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "Asignación sospechosa",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def load_dotenv(path=".env"):
    """Carga variables de un archivo .env sin dependencias externas."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def run_git(*args):
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Error al ejecutar git")
    return result.stdout


def get_diff(use_all):
    """Devuelve el diff de staging; con --all usa también los cambios sin añadir."""
    diff = run_git("diff", "--cached")
    if not diff.strip() and use_all:
        diff = run_git("diff")
    return diff


def find_secrets(diff):
    """Busca posibles secretos solo en las líneas añadidas (+) del diff."""
    findings = []
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(name)
    return sorted(set(findings))


def truncate(diff):
    if len(diff) <= MAX_DIFF_CHARS:
        return diff
    return diff[:MAX_DIFF_CHARS] + "\n... [diff recortado] ..."


def clean_message(text):
    """Quita comillas y bloques de código que a veces añaden los modelos."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    return text.strip("\"'` \n")


# ---------------------------------------------------------------------------
# Llamadas a las APIs
# ---------------------------------------------------------------------------
def post_json(url, headers, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"La API respondió {err.code}: {detail}") from None
    except urllib.error.URLError as err:
        raise RuntimeError(f"No se pudo conectar: {err.reason}") from None


def ask_gemini(api_key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    data = post_json(
        url,
        {"x-goog-api-key": api_key},
        {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        },
    )
    return data["candidates"][0]["content"]["parts"][0]["text"]


def ask_openai(api_key, model, prompt):
    data = post_json(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {api_key}"},
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
    )
    return data["choices"][0]["message"]["content"]


def ask_anthropic(api_key, model, prompt):
    data = post_json(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        {
            "model": model,
            "max_tokens": 300,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return data["content"][0]["text"]


ASKERS = {"gemini": ask_gemini, "openai": ask_openai, "anthropic": ask_anthropic}


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Genera mensajes de commit (Conventional Commits) con IA."
    )
    parser.add_argument(
        "--provider",
        choices=PROVIDERS.keys(),
        default=os.environ.get("COMMIT_AI_PROVIDER", "gemini"),
        help="Proveedor de IA (por defecto: gemini)",
    )
    parser.add_argument("--model", help="Modelo a usar (sobrescribe el valor por defecto)")
    parser.add_argument("--commit", action="store_true", help="Hacer el commit tras confirmar")
    parser.add_argument(
        "--all", action="store_true", help="Si no hay cambios en staging, usar los no añadidos"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continuar aunque se detecten posibles secretos (no recomendado)",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()
    config = PROVIDERS[args.provider]

    api_key = os.environ.get(config["env_key"])
    if not api_key:
        sys.exit(
            f"Falta la variable {config['env_key']}. Copia .env.example a .env y añade tu clave."
        )

    try:
        diff = get_diff(args.all)
    except RuntimeError as err:
        sys.exit(f"Error con git: {err}")

    if not diff.strip():
        sys.exit("No hay cambios. Usa 'git add' primero (o la opción --all).")

    secrets = find_secrets(diff)
    if secrets and not args.force:
        sys.exit(
            "Posibles secretos detectados en tus cambios (" + ", ".join(secrets) + ").\n"
            "No se envió nada a la IA. Quítalos del código, muévelos a .env y vuelve a intentar."
        )

    model = args.model or os.environ.get("COMMIT_AI_MODEL") or config["default_model"]
    prompt = "Escribe el mensaje de commit para estos cambios:\n\n" + truncate(diff)

    try:
        message = clean_message(ASKERS[args.provider](api_key, model, prompt))
    except (RuntimeError, KeyError, IndexError) as err:
        sys.exit(f"No se pudo generar el mensaje: {err}")

    print("\nMensaje sugerido:\n")
    print(message)
    print()

    if args.commit:
        answer = input("¿Hacer commit con este mensaje? [s/N] ").strip().lower()
        if answer in ("s", "si", "sí", "y", "yes"):
            run_git("commit", "-m", message)
            print("Commit realizado.")
        else:
            print("Cancelado, no se hizo ningún commit.")


if __name__ == "__main__":
    main()
