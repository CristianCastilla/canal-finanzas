# Economía Ilustrada — canal automatizado (coste 0 €)

Pipeline para producir y publicar un canal de finanzas con IA: **guion → voz → ilustraciones → gráficos → montaje → miniatura → subida programada a YouTube**. Todo con servicios gratuitos y pensado para dedicarle **1-2 horas por semana**.

> Los tres guiones de ejemplo de `data/samples/` ya están listos para renderizar. No necesitas clave de IA para probar el vídeo.

---

## Cómo funciona

```
RSS + Yahoo Finance
        │
        ▼
  Guion con IA (Gemini/Groq)  ──►  data/queue.json  ──►  TÚ revisas y apruebas
                                                              │
                                                              ▼
              voz (Edge-TTS/Piper) + imágenes (Pollinations) + gráficos (matplotlib)
                                                              │
                                                              ▼
                     FFmpeg: Ken Burns + subtítulos + música + miniatura
                                                              │
                                                              ▼
                     YouTube API: subida privada + publicación programada
```

El único paso manual es **revisar y aprobar**. Es también el paso que evita que YouTube considere el canal "contenido producido en masa" (política de julio de 2025).

---

## 1. Lo que necesitas (todo gratis)

| Servicio | Para qué | Límite |
|---|---|---|
| [Google AI Studio](https://aistudio.google.com/apikey) | Guiones | Cupo diario gratuito |
| [Groq](https://console.groq.com/keys) | Alternativa de guiones | Cupo diario gratuito |
| [YouTube Data API v3](https://console.cloud.google.com/) | Subir vídeos | 10.000 unidades/día; 1.600 por subida |
| [Pollinations](https://pollinations.ai/) | Ilustraciones | 1 imagen/45 s por IP (gratis) |
| GitHub Actions | Ejecutar todo solo | Gratis en repos públicos |
| Telegram (opcional) | Avisos | Gratis |

**Coste total: 0 €.** Solo necesitas una cuenta de Google (la del canal) y una de GitHub.

---

## 2. Puesta en marcha sin instalar nada (recomendada)

1. Crea un repositorio en GitHub. Si es **público**, los minutos de Actions son ilimitados. Si es privado, tienes 2.000 min/mes (suficiente: el uso real ronda 1-2 h/mes).
2. Sube esta carpeta al repo. Si no tienes Git instalado, usa **GitHub Desktop** o el botón *Add file → Upload files* (arrastra la carpeta completa, incluida `.github`).
3. En **Settings → Secrets and variables → Actions**, añade:
   - `GEMINI_API_KEY` — obligatorio para generar guiones.
   - `YOUTUBE_TOKEN_JSON` — obligatorio para publicar (ver paso 3).
   - Opcionales: `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `POLLINATIONS_TOKEN`.
4. En **Settings → Actions → General → Workflow permissions**, marca **Read and write permissions** (el workflow guarda la cola en el repo).
5. Ve a **Actions → Generar guiones → Run workflow**. En 2-5 minutos tendrás guiones nuevos en `data/queue.json`.
6. Abre `data/queue.json`, revisa el título, la descripción y las escenas. Cambia `"status": "draft"` por `"status": "approved"` en el que quieras publicar (o usa el comando local del paso 4).
7. Ve a **Actions → Renderizar y publicar → Run workflow**. Renderiza, sube el vídeo como privado y lo programa para las 16:00 UTC (18:00 en España en verano).
8. El vídeo se publica solo. El workflow guarda el estado en `data/queue.json` y deja el mp4 como *artifact* durante 7 días.

> Si prefieres publicar ya, ejecuta el workflow con `id` y `force: true`; o en local: `python -m src.main publish ID --at 2026-10-30T18:00`.

### Aprobar desde el móvil (Telegram, opcional)

1. Habla con [@BotFather](https://t.me/BotFather), crea un bot y copia el token.
2. Mándale un mensaje al bot y abre `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver tu `chat_id` (o usa [@userinfobot](https://t.me/userinfobot)).
3. Añade los secrets `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
4. El workflow **Aprobaciones Telegram** revisa cada hora los botones. También puedes escribirle `/lista`, `/aprobar <id>` o `/rechazar <id>`.

Cuando se genera un guion, recibes el título, el gancho y dos botones: **Aprobar** / **Rechazar**. Al aprobar, el siguiente pase de publicación lo renderiza y lo programa.

### Calendario por defecto

- **Domingos 05:00 UTC**: genera 1 vídeo largo + 2 shorts.
- **Todos los días 14:00 UTC**: si hay un guion aprobado, lo renderiza y lo programa.
- Tú solo revisas el domingo o el lunes (30-45 min) y apruebas.

---

## 3. Autorizar YouTube (una sola vez)

1. Entra en [Google Cloud Console](https://console.cloud.google.com/) y crea un proyecto.
2. **APIs y servicios → Biblioteca → YouTube Data API v3 → Habilitar**.
3. **Pantalla de consentimiento OAuth**:
   - Tipo: *External*.
   - Rellena nombre, email y añade tu cuenta de Google como *usuario de prueba*.
   - Cuando funcione, cambia el estado a **En producción**. Si lo dejas en *Testing*, el refresh token caduca a los 7 días y tendrás que reautorizar cada semana.
4. **Credenciales → Crear credenciales → ID de cliente OAuth → Aplicación de escritorio**. Descarga el JSON y guárdalo como `client_secret.json` (no lo subas al repo; ya está en `.gitignore`).
5. Genera el token:

```bash
python scripts/auth_youtube.py client_secret.json
```

Se abre el navegador, aceptas y el script imprime un JSON. **Copia ese JSON completo** en el secret `YOUTUBE_TOKEN_JSON`.

Si no tienes Python local, usa Colab:

```python
!pip install -q google-auth-oauthlib
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    ["https://www.googleapis.com/auth/youtube.upload",
     "https://www.googleapis.com/auth/youtube"],
)
creds = flow.run_console()
print(creds.to_json())
```

> La app mostrará "Google no ha verificado esta aplicación". Es normal: eres el único usuario. Pulsa *Configuración avanzada → Ir a la app*.

---

## 4. Uso en local (opcional)

Necesario solo si quieres renderizar en tu PC o revisar guiones con comandos.

**Windows:**

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Gyan.FFmpeg
git clone <tu-repo>
cd "Canal finanzas"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Rellena `.env` con tus claves y comprueba el entorno:

```bash
python -m src.main doctor
```

**macOS / Linux:**

```bash
brew install python ffmpeg        # macOS
sudo apt install python3 python3-venv ffmpeg fonts-dejavu   # Debian/Ubuntu
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Comandos

```bash
python -m src.main samples                 # recupera los 3 guiones de ejemplo
python -m src.main list                    # ver la cola
python -m src.main show <id>               # leer un guion completo
python -m src.main approve <id>            # aprobar
python -m src.main reject <id>             # descartar
python -m src.main render <id>             # solo renderizar (prueba)
python -m src.main render <id> --force     # rehacer
python -m src.main publish <id>            # renderizar + subir programado
python -m src.main publish <id> --at 2026-11-02T18:00
python -m src.main run                     # publicar el siguiente aprobado
python -m src.main generate --weekly       # 1 largo + 2 shorts
python -m src.main telegram                # procesa botones de Telegram
python -m src.main doctor                  # diagnóstico
```

Los vídeos quedan en `out/<id>/video.mp4` y `out/<id>/thumb.jpg`.

---

## 5. Configuración

Todo está en `config.yaml`:

| Clave | Qué controla |
|---|---|
| `channel.name` | Marca de agua y nombre del canal |
| `weekly.long` / `weekly.shorts` | Cuántos genera cada domingo |
| `formats.*.width/height/fps` | 1920×1080 o 1080×1920 |
| `llm.provider` / `llm.model` | Gemini o Groq y modelo |
| `tts.engine` | `edge` (fácil) o `piper` (local) |
| `tts.voice` | `es-ES-AlvaroNeural`, `es-ES-ElviraNeural`, `es-MX-JorgeNeural`, `es-AR-TomasNeural`… |
| `images.style` | Estilo visual. Cámbialo y todo el canal cambia |
| `images.model` | `flux` (calidad) o `turbo` (rápido) |
| `video.music` | Ruta a un mp3 con licencia (opcional) |
| `youtube.publish_hour_utc` | Hora de publicación |
| `youtube.tags` | Etiquetas por defecto |

### Voz

- **Edge-TTS**: gratis y sin clave. Es el predeterminado. Ojo: usa un endpoint no oficial de Microsoft; para un canal monetizado es una zona gris. Si el canal crece, cambia a Piper o graba tu voz.
- **Piper**: 100 % local y open source.

```bash
pip install piper-tts
# descarga un modelo es_ES de https://huggingface.co/rhasspy/piper-voices
```

```yaml
tts:
  engine: "piper"
  piper_model: "assets/voices/es_ES-sharvard-medium.onnx"
```

### Imágenes

Pollinations gratuito permite **1 imagen cada 45 s**. El pipeline espera automáticamente. Si tienes una *pollen key* gratuita, añádela como `POLLINATIONS_TOKEN` y desaparece la espera y la marca de agua (el pipeline tapa la marca con una etiqueta del canal).

Si una imagen falla, se genera un fondo abstracto con la paleta del canal: el vídeo nunca se rompe.

### Música

Descarga una pista de la [YouTube Audio Library](https://www.youtube.com/audiolibrary) o de [Pixabay Music](https://pixabay.com/music/), guárdala como `assets/music/fondo.mp3` y pon:

```yaml
video:
  music: "assets/music/fondo.mp3"
  music_volume: 0.07
```

No subas música con copyright al repo.

> En GitHub Actions la música no está en el repositorio (los `.mp3` están ignorados). Si quieres música también en la nube, usa una pista con licencia y elimina `assets/music/*.mp3` del `.gitignore`.

---

## 6. Reglas para no perder la monetización

La política de **contenido no auténtico** de YouTube (actualizada en julio de 2025) excluye el contenido "producido en masa" y repetitivo. Un canal de IA que solo lee titulares no cobra. Este proyecto está diseñado para lo contrario:

- **Aporta criterio propio**: el prompt obliga a una tesis, contexto y conclusión, no un resumen de noticias.
- **Estilo propio**: paleta, tipografía y formato fijos. No copies personajes ni el estilo de NOTICIAS ILUSTRADAS.
- **Datos reales**: gráficos de Yahoo Finance y fuentes citadas.
- **Revisa antes de publicar**: datos, fechas, cifras y sentido común. La IA se equivoca.
- **Nada de promesas**: ni "esto va a subir" ni rentabilidades garantizadas. El aviso de no asesoramiento va en todas las descripciones.
- **Marca el contenido sintético** en YouTube Studio si la voz o las imágenes parecen reales.
- **No uses fotos de prensa**: todas las imágenes son ilustraciones generadas.
- **Constancia**: 1.000 suscriptores + 4.000 horas/año (o 10 M vistas de shorts/90 días). En finanzas el CPM es alto, pero la competencia también. Piensa en 6-12 meses.

---

## 7. Costes y límites reales

| Recurso | Límite | ¿Suficiente? |
|---|---|---|
| YouTube API | 10.000 uds/día; 1.600 por subida | 6 subidas/día |
| GitHub Actions (público) | Ilimitado | Sí |
| GitHub Actions (privado) | 2.000 min/mes | 1 largo + 2 shorts/semana ≈ 200 min/mes |
| Gemini free | Cupo diario | 3 guiones/semana |
| Pollinations free | 1 imagen/45 s | 10-12 imágenes ≈ 10 min |
| Render 1080p | 10-25 min por vídeo | Cabe en el timeout de 90 min |

**El coste real es tu tiempo de revisión: 30-45 min/semana.**

---

## 8. Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `Pollinations HTTP 402` | Límite gratuito. El pipeline espera 50 s. Añade `POLLINATIONS_TOKEN` para evitarlo. |
| `Edge-TTS ... Cannot connect` | Fallo puntual de red. Reintenta; si persiste, cambia a Piper. |
| `ffmpeg: NO ENCONTRADO` | Instala FFmpeg o define `FFMPEG_BIN` con la ruta completa. |
| `invalid_grant` al subir | Refresh token caducado. Reautoriza y actualiza `YOUTUBE_TOKEN_JSON`; pon la app OAuth en producción. |
| `quotaExceeded` | Límite diario de YouTube. Espera a las 00:00 PT o pide más cuota. |
| El workflow no puede hacer push | Settings → Actions → General → Workflow permissions → Read and write. |
| El vídeo sale con la marca de Pollinations | Pon `POLLINATIONS_TOKEN` o baja el tamaño de la etiqueta; el pipeline la tapa. |
| Quiero otro estilo visual | Cambia `images.style` y `channel.name`; borra `out/` y regenera. |

---

## 9. Estructura

```
Canal finanzas/
├─ config.yaml                 # todo lo configurable
├─ prompts/                    # personalidad y reglas del guionista
├─ src/
│  ├─ main.py                  # CLI
│  ├─ script.py / llm.py       # generación de guiones
│  ├─ ideas.py / market.py     # titulares y datos
│  ├─ tts.py / images.py       # voz e ilustraciones
│  ├─ charts.py                # gráficos de mercado
│  ├─ render.py                # FFmpeg
│  ├─ thumbnail.py             # miniaturas
│  ├─ publish.py               # YouTube API
│  └─ store.py                 # cola en data/queue.json
├─ data/samples/               # 3 guiones listos para probar
├─ scripts/auth_youtube.py     # autorización OAuth
├─ .github/workflows/          # generación semanal + publicación diaria
└─ out/                        # vídeos renderizados (ignorado por git)
```

---

## 10. Siguientes pasos (cuando funcione)

1. **Cortar los shorts del vídeo largo** automáticamente (los 45 s con más gancho) en vez de generarlos aparte.
2. **Doblaje a inglés** con la misma pipeline y otro canal (el CPM en inglés suele ser mayor).
3. **A/B de miniaturas**: generar 3 y elegir por CTR en YouTube Analytics.

---

*Contenido educativo. No es asesoramiento financiero.*
