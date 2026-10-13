# Compilar AudioLocal para Mac

El binario publicado es para Apple Silicon y macOS 13.5 o posterior. Incluye el
runtime Python, Tcl/Tk, el ejecutable oficial yt-dlp, Node y FFmpeg. Los programas
de descarga y conversión se ejecutan como procesos separados del motor de la app.

Para compilar necesitas un Mac Apple Silicon con las herramientas de línea de
comandos de Xcode (Clang y make), Python con Tkinter e internet. La distribución
1.0.0 se construyó con Python 3.12.14, Tcl/Tk 9.0.4 y PyInstaller 6.22.0. Usa ese
runtime para reproducir la selección de bibliotecas; si lo cambias, revisa los
requisitos de macOS y los avisos de licencia del binario resultante.

Desde la raíz del repositorio o del ZIP de fuentes:

```bash
bash build-mac.sh
```

El script descarga herramientas oficiales con versiones fijadas y verifica las
sumas de yt-dlp y Node. Prepara su propio entorno `.build-venv`. FFmpeg 7.1 se
compila desde fuentes, con libmp3lame 3.100, sin GPL, nonfree ni bibliotecas externas
de vídeo. La línea exacta de configuración se conserva en `build-ffmpeg.sh`.
La compilación usa LAME estático; los archivos originales completos y el script
permiten recompilar FFmpeg con una versión modificada de esa biblioteca.

El resultado es `dist/AudioLocal.app`. No está notarizado y PyInstaller lo firma
ad hoc. No cambies el contenido del bundle después de verificar y empaquetar su
firma. Los binarios oficiales se mantienen como ejecutables separados; el archivo
de yt-dlp se recoge como dato para conservar su archivo PyInstaller incrustado.

El motor conserva `python -m yt_dlp` al ejecutarse desde fuentes. En el bundle usa
las herramientas incluidas. La salida inicial es `~/Downloads/AudioLocal`.

Para ejecutar desde fuentes:

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 src/app.py
```

Para comprobar conversiones, procesos y ventana desde el bundle:

```bash
env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV -u TCL_LIBRARY -u TK_LIBRARY \
  PATH=/usr/bin:/bin dist/AudioLocal.app/Contents/MacOS/AudioLocal \
  --verify-package /tmp/audiolocal-verificacion.json
```

El modo de comprobación genera un tono temporal, convierte a tres calidades,
cancela procesos Node, abre y cierra la ventana y escribe un informe local.
No descarga canciones ni utiliza cuentas o sesiones de navegadores.

Las fuentes de FFmpeg, LAME, yt-dlp y Mutagen incluidas en el ZIP de fuentes se
conservan sin modificaciones. Las fuentes y avisos de los demás componentes
están enlazados en `licenses/FUENTES.txt`. Publica ese ZIP junto al binario.
