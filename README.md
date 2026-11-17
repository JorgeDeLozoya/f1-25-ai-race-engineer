# AI Race Engineer para F1 25 / 26 (Swofty Addon + Standalone)

Ingeniero de pista interactivo por voz con IA para **F1 25 / F1 26** en PC.

## Características
- **Lectura en tiempo real del puerto UDP (`20777`, formato `2025`)**: Posiciones, gaps, neumáticos (compuesto, edad, desgaste y temperatura por rueda), daños en alerones/fondo, combustible, ERS, Safety Car / VSC y previsión meteorológica.
- **Bilingüe por voz (Español e Inglés)**:
  - Español: voz neuronal `es-ES-AlvaroNeural`
  - Inglés: voz neuronal británica `en-GB-RyanNeural`
  - Detecta automáticamente en qué idioma le hablas y te responde en ese idioma.
- **Efecto DSP de Radio de Fórmula 1**:
  - Doble pitido (chirp FIA) al abrir radio, filtro paso banda de muro de boxes (`340 Hz – 3300 Hz`), compresión/saturación analógica y cola de *squelch* al cortar.
- **Personalidad de Ingeniero Real + Control de "Off-Topic"**:
  - Si le preguntas *"¿Cuáles son las 5 primeras posiciones?"* o *"What are the top 5 positions?"*, te canta el Top 5 real de la sesión con sus diferencias.
  - Si le dices algo que **no viene a cuento de la carrera** (comida, películas, fútbol, chistes...), te pega la bronca de ingeniero para que te centres en conducir y mires a la pista.
- **Activación continua por Palabra Clave ("Wake Word") + Push-To-Talk opcional**:
  - Di **"Radio"**, **"Ingeniero"**, **"Engineer"**, **"Box"** o **"Marc"** seguido de tu pregunta (o di solo *"Radio"*, espera al pitido de confirmación y haz tu pregunta).
  - También puedes pulsar `F9` en cualquier momento.

## Cómo usar
1. **Activar Telemetría UDP en F1 25**:
   - En el juego ve a `Settings` -> `Telemetry Settings`:
     - **UDP Telemetry**: `On`
     - **UDP Port**: `20777`
     - **UDP Format**: `2025`
2. **En Swofty Launcher**:
   - Arrastra el archivo `ai_engineer.swoftyaddon` a la ventana de **Swofty Launcher** (o instala la carpeta `ai_race_engineer`).
   - En la barra lateral, dentro de **ADDON PANELS -> Race Engineer**, puedes pegar tu **Google Gemini API Key**, elegir idioma, palabras clave y probar la radio en directo.
3. **Modo directo (con o sin Swofty)**:
   - Haz doble clic en `run_engineer.bat` (o ejecuta `.venv\Scripts\python -m engineer`).

---
**Autor**: JorgeDelo · *Sugerencias, mejoras, nuevas peticiones o reporte de fallos son siempre bienvenidos en Overtake.gg!*
