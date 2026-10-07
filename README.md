# commit-ai

Genera mensajes de commit en formato [Conventional Commits](https://www.conventionalcommits.org/es/) a partir de tus cambios en git, usando **Gemini**, **OpenAI** o **Anthropic (Claude)**.

- Un solo archivo de Python, **sin dependencias externas**.
- Cambias de proveedor con una opción o una variable de entorno.
- **Protección de secretos:** si tus cambios contienen algo que parece una API key o contraseña, el script se detiene y no envía nada a la IA.

## Requisitos

- Python 3.8 o superior
- Git
- Una API key de al menos uno de los proveedores (Gemini tiene un plan gratuito en [Google AI Studio](https://aistudio.google.com/))

> Las suscripciones de chat (por ejemplo, ChatGPT Plus o Gemini Advanced) no incluyen acceso por API. Necesitas una API key aparte.

## Instalación

```bash
git clone https://github.com/AngelDavidDT/commit-ai.git
cd commit-ai
cp .env.example .env
```

Abre `.env` y pega tu clave en la variable del proveedor que vayas a usar. El archivo `.env` está en `.gitignore`, así que nunca se sube a GitHub.

## Uso

Desde cualquier repositorio git, añade tus cambios y ejecuta:

```bash
git add .
python /ruta/a/commit_ai.py
```

Opciones:

| Opción | Qué hace |
| --- | --- |
| `--provider gemini\|openai\|anthropic` | Elige el proveedor (por defecto `gemini`) |
| `--model NOMBRE` | Fuerza un modelo concreto |
| `--commit` | Hace el commit tras pedirte confirmación |
| `--all` | Si no hay cambios en staging, usa los no añadidos |
| `--force` | Continúa aunque se detecten posibles secretos (no recomendado) |

Ejemplo:

```bash
python commit_ai.py --provider anthropic --commit
```

Tip: crea un alias en tu terminal, por ejemplo `alias gc="python ~/commit-ai/commit_ai.py --commit"`.

## Seguridad y privacidad

- Se envía a la IA **solo el diff** de tus cambios, recortado a 12 000 caracteres.
- Antes de enviarlo se buscan patrones de claves y contraseñas en las líneas añadidas. Si hay coincidencias, se aborta.
- La detección es básica y no es infalible: revisa siempre lo que subes.
- Nunca subas tu archivo `.env`. Si una clave llega a un repositorio público, revócala y genera otra.

## Roadmap

- [ ] Integración como git hook (`prepare-commit-msg`) para que el mensaje aparezca solo al hacer `git commit`
- [ ] Empaquetado para instalar con `pip install commit-ai`
- [ ] GIF de demostración en este README
- [ ] Más proveedores y soporte para elegir el idioma del mensaje

## Contribuir

Las ideas y los pull requests son bienvenidos. Si quieres ayudar con algo del roadmap, abre un issue y lo hablamos.

## Licencia

[MIT](LICENSE)
