"""Obtiene el refresh token de YouTube. Se ejecuta UNA vez en tu equipo o en Colab.

Uso:
    python scripts/auth_youtube.py client_secret.json
    python scripts/auth_youtube.py client_secret.json --console   # sin navegador local

Copia el JSON que imprime en el secret YOUTUBE_TOKEN_JSON de GitHub.
"""
from __future__ import annotations

import argparse
import json
import sys

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Autoriza el canal de YouTube")
    parser.add_argument("client_secret", help="JSON de credenciales OAuth de escritorio")
    parser.add_argument("--console", action="store_true", help="Muestra un enlace en vez de abrir navegador")
    args = parser.parse_args()

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    if args.console:
        credentials = flow.run_console()
    else:
        credentials = flow.run_local_server(port=0, prompt="consent",
                                            authorization_prompt_message="")
    print("\nCopia TODO este JSON en el secret YOUTUBE_TOKEN_JSON:\n", file=sys.stderr)
    print(json.dumps(json.loads(credentials.to_json()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
