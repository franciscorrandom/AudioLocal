"""Interfaz de escritorio de AudioLocal.

El motor trabaja en un hilo y publica eventos en una cola. Únicamente el hilo
principal lee o modifica widgets de Tk.
"""

from __future__ import annotations

import os
import platform
import queue
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from engine import DownloadEngine, DownloadError, DownloadRequest
from windows_support import downloads_directory, window_work_area


APP_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIRECTORY = downloads_directory() / "AudioLocal"
FONT_FAMILY = "Segoe UI" if platform.system() == "Windows" else "Helvetica"
COLORS = {
    "background": "#0B1220",
    "card": "#121D2F",
    "field": "#0D1727",
    "border": "#27384C",
    "text": "#ECF3F8",
    "muted": "#9AADBF",
    "accent": "#67DCC7",
    "accent_hover": "#8BE8D7",
    "error": "#F6A89E",
}


class AudioLocalApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AudioLocal — YouTube a MP3")
        area = window_work_area()
        if area:
            # CustomTkinter geometry uses logical dimensions and applies the
            # monitor's DPI scale itself; Windows work-area dimensions are pixels.
            scale = self._get_window_scaling()
            width = max(320, min(1080, int(area[0] / scale) - 48))
            height = max(320, min(840, int(area[1] / scale) - 60))
            self.geometry(f"{width}x{height}")
            self.minsize(min(960, width), min(600, height))
        else:
            self.geometry("1080x840")
            self.minsize(960, 760)
        self.configure(fg_color=COLORS["background"])

        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._engine: DownloadEngine | None = None
        self._worker: threading.Thread | None = None
        self._running = False
        self._cancel_requested = False
        self._close_when_done = False
        self._errors = 0
        self._completed = 0
        self._total = 0
        self._known_files: set[str] = set()
        self._log_lines = 0

        self.output_directory = ctk.StringVar(value=str(DEFAULT_OUTPUT_DIRECTORY))
        self.bitrate = ctk.StringVar(value="192")
        self.add_metadata = ctk.BooleanVar(value=True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_content()
        self._build_footer()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Command-Return>", lambda _event: self._start_download())
        self.bind("<Control-Return>", lambda _event: self._start_download())
        self.after(80, self._consume_events)

    def _card(self, parent: Any) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            corner_radius=18,
            fg_color=COLORS["card"],
            border_width=1,
            border_color=COLORS["border"],
        )

    def _label(self, parent: Any, text: str, size: int = 14, **kwargs: Any) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent,
            text=text,
            text_color=COLORS["text"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=size),
            **kwargs,
        )

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 18))
        header.grid_columnconfigure(1, weight=1)
        mark = ctk.CTkLabel(
            header,
            text="AL",
            width=54,
            height=54,
            corner_radius=16,
            fg_color=COLORS["accent"],
            text_color=COLORS["background"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=21, weight="bold"),
        )
        mark.grid(row=0, column=0, rowspan=2, padx=(0, 15))
        self._label(header, "AudioLocal", size=29, anchor="w").grid(
            row=0, column=1, sticky="w"
        )
        subtitle = self._label(header, "Tus enlaces, convertidos en audio.", size=14, anchor="w")
        subtitle.configure(text_color=COLORS["muted"])
        subtitle.grid(row=1, column=1, sticky="w", pady=(0, 2))
        badge = self._label(header, "MP3  /  EN TU EQUIPO", size=11)
        badge.configure(text_color=COLORS["accent"])
        badge.grid(row=0, column=2, rowspan=2, padx=(12, 0))

    def _build_content(self) -> None:
        # Scrolling keeps the controls accessible on laptop displays and at
        # Windows' larger text/DPI settings, without shrinking the form fields.
        if platform.system() == "Windows":
            content = ctk.CTkScrollableFrame(
                self, orientation="vertical", corner_radius=0,
                fg_color=COLORS["background"],
            )
        else:
            content = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame = content
        content.grid(row=1, column=0, sticky="nsew", padx=28)
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=3)
        content.grid_rowconfigure(1, weight=2)

        links_card = self._card(content)
        links_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
        links_card.grid_columnconfigure(0, weight=1)
        links_card.grid_rowconfigure(2, weight=1)
        self._label(links_card, "01   Pega tus enlaces", size=18, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=22, pady=(20, 3)
        )
        hint = self._label(links_card, "Un enlace de YouTube por línea.", anchor="w")
        hint.configure(text_color=COLORS["muted"])
        hint.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 14))
        self.links_box = ctk.CTkTextbox(
            links_card,
            height=140,
            corner_radius=10,
            fg_color=COLORS["field"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            wrap="word",
        )
        self.links_box.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 14))
        actions = ctk.CTkFrame(links_card, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=22, pady=(0, 22))
        actions.grid_columnconfigure(0, weight=1)
        self.download_button = ctk.CTkButton(
            actions,
            text="Descargar MP3",
            height=44,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["background"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            command=self._start_download,
        )
        self.download_button.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.cancel_button = ctk.CTkButton(
            actions,
            text="Cancelar",
            width=100,
            height=44,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#354A62",
            text_color=COLORS["text"],
            state="disabled",
            command=self._cancel_download,
        )
        self.cancel_button.grid(row=0, column=1)

        options = self._card(content)
        options.grid(row=0, column=1, sticky="nsew", pady=(0, 14))
        options.grid_columnconfigure(0, weight=1)
        self._label(options, "02   Configura el audio", size=18, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=22, pady=(20, 18)
        )
        self._label(options, "Carpeta de salida", anchor="w").grid(
            row=1, column=0, sticky="ew", padx=22, pady=(0, 6)
        )
        self.folder_entry = ctk.CTkEntry(
            options,
            textvariable=self.output_directory,
            height=38,
            corner_radius=8,
            fg_color=COLORS["field"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.folder_entry.grid(row=2, column=0, sticky="ew", padx=22)
        self.choose_folder_button = ctk.CTkButton(
            options,
            text="Elegir carpeta…",
            height=32,
            fg_color=COLORS["border"],
            hover_color="#354A62",
            command=self._choose_output_directory,
        )
        self.choose_folder_button.grid(row=3, column=0, sticky="w", padx=22, pady=(8, 18))
        self._label(options, "Calidad del MP3", anchor="w").grid(
            row=4, column=0, sticky="ew", padx=22, pady=(0, 6)
        )
        self.quality_picker = ctk.CTkSegmentedButton(
            options,
            values=["128", "192", "320"],
            variable=self.bitrate,
            height=36,
            selected_color="#285A5D",
            selected_hover_color="#347371",
            unselected_color=COLORS["field"],
            unselected_hover_color=COLORS["border"],
            text_color=COLORS["text"],
            text_color_disabled=COLORS["muted"],
        )
        self.quality_picker.grid(row=5, column=0, sticky="ew", padx=22)
        quality_hint = self._label(options, "kbps · 192 es una opción equilibrada", size=12, anchor="w")
        quality_hint.configure(text_color=COLORS["muted"])
        quality_hint.grid(row=6, column=0, sticky="ew", padx=22, pady=(4, 16))
        self.metadata_switch = ctk.CTkSwitch(
            options,
            text="Incluir metadatos",
            variable=self.add_metadata,
            progress_color=COLORS["accent"],
            button_color=COLORS["text"],
            button_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
        )
        self.metadata_switch.grid(row=7, column=0, sticky="w", padx=22, pady=(0, 22))

        activity = self._card(content)
        activity.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        activity.grid_columnconfigure(0, weight=1)
        activity.grid_rowconfigure(4, weight=1)
        self._label(activity, "Actividad", size=18, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=22, pady=(18, 6)
        )
        self.status_label = self._label(activity, "Listo para empezar.", size=13, anchor="w")
        self.status_label.configure(text_color=COLORS["muted"], wraplength=520)
        self.status_label.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 10))
        self.progress_bar = ctk.CTkProgressBar(
            activity,
            height=7,
            fg_color=COLORS["border"],
            progress_color=COLORS["accent"],
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=22)
        self.progress_label = self._label(activity, "0 archivos guardados", size=12, anchor="w")
        self.progress_label.configure(text_color=COLORS["muted"])
        self.progress_label.grid(row=3, column=0, sticky="ew", padx=22, pady=(6, 10))
        self.log_box = ctk.CTkTextbox(
            activity,
            height=100,
            corner_radius=9,
            fg_color=COLORS["field"],
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            wrap="word",
            state="disabled",
        )
        self.log_box.grid(row=4, column=0, sticky="nsew", padx=22, pady=(0, 20))

        results = self._card(content)
        results.grid(row=1, column=1, sticky="nsew")
        results.grid_columnconfigure(0, weight=1)
        results.grid_rowconfigure(1, weight=1)
        self._label(results, "Archivos guardados", size=18, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=22, pady=(18, 10)
        )
        self.files_list = ctk.CTkScrollableFrame(
            results,
            height=110,
            corner_radius=9,
            fg_color=COLORS["field"],
        )
        self.files_list.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.files_list.grid_columnconfigure(0, weight=1)
        self.empty_files_label = self._label(
            self.files_list,
            "Los MP3 terminados aparecerán aquí.",
            size=13,
            wraplength=300,
            justify="left",
        )
        self.empty_files_label.configure(text_color=COLORS["muted"])
        self.empty_files_label.grid(row=0, column=0, sticky="w", padx=8, pady=12)
        self.open_folder_button = ctk.CTkButton(
            results,
            text="Abrir carpeta de salida",
            height=36,
            fg_color=COLORS["border"],
            hover_color="#354A62",
            command=self._open_output_directory,
        )
        self.open_folder_button.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 20))

    def _build_footer(self) -> None:
        footer = self._label(self, "AudioLocal  ·  YouTube a MP3", size=11, anchor="w")
        footer.configure(text_color=COLORS["muted"])
        footer.grid(row=2, column=0, sticky="ew", padx=30, pady=(12, 16))

    def _choose_output_directory(self) -> None:
        current = Path(self.output_directory.get()).expanduser()
        initial_directory = current if current.is_dir() else downloads_directory()
        chosen = filedialog.askdirectory(
            parent=self,
            title="Elegir carpeta para los MP3",
            initialdir=str(initial_directory),
            mustexist=True,
        )
        if chosen:
            self.output_directory.set(chosen)

    def _set_running(self, running: bool) -> None:
        self._running = running
        input_state = "disabled" if running else "normal"
        for widget in (
            self.links_box,
            self.folder_entry,
            self.choose_folder_button,
            self.quality_picker,
            self.metadata_switch,
            self.download_button,
        ):
            widget.configure(state=input_state)
        self.cancel_button.configure(state="normal" if running else "disabled")
        self.download_button.configure(text="Descargando…" if running else "Descargar MP3")

    def _start_download(self) -> None:
        if self._running:
            return
        urls = [line.strip() for line in self.links_box.get("1.0", "end").splitlines() if line.strip()]
        if not urls:
            self._set_status("Pega al menos un enlace para comenzar.")
            self.links_box.focus_set()
            return
        directory = self.output_directory.get().strip()
        if not directory:
            self._set_status("Elige una carpeta para guardar los MP3.")
            self.folder_entry.focus_set()
            return

        request = DownloadRequest(
            urls=urls,
            output_dir=Path(directory).expanduser(),
            bitrate=int(self.bitrate.get()),
            metadata=bool(self.add_metadata.get()),
        )
        done_signal = threading.Event()

        def enqueue(event: dict[str, Any]) -> None:
            copied_event = dict(event)
            if copied_event.get("type") == "done":
                done_signal.set()
            self._events.put(copied_event)

        try:
            engine = DownloadEngine(on_event=enqueue)
        except Exception as exc:
            self._set_status(f"No se pudo iniciar la descarga: {exc}", error=True)
            self._log(str(exc))
            return

        self._engine = engine
        self._cancel_requested = False
        self._errors = 0
        self._completed = 0
        self._total = len(urls)
        self._set_running(True)
        self.progress_bar.set(0)
        self._update_progress_label()
        self._set_status("Preparando la descarga…")
        self._log(f"Iniciando {self._total} enlace(s) a {request.bitrate} kbps.")
        self._worker = threading.Thread(
            target=self._run_engine,
            args=(engine, request, enqueue, done_signal),
            name="audiolocal-download",
            daemon=True,
        )
        self._worker.start()

    @staticmethod
    def _run_engine(
        engine: DownloadEngine,
        request: DownloadRequest,
        enqueue: Any,
        done_signal: threading.Event,
    ) -> None:
        try:
            engine.run(request)
        except DownloadError as exc:
            enqueue({"type": "error", "message": str(exc)})
        except Exception as exc:
            enqueue({"type": "error", "message": f"La descarga se interrumpió: {exc}"})
        finally:
            if not done_signal.is_set():
                enqueue({"type": "done"})

    def _cancel_download(self) -> None:
        if not self._running or self._engine is None or self._cancel_requested:
            return
        self._cancel_requested = True
        self.cancel_button.configure(state="disabled", text="Cancelando…")
        self._set_status("Cancelando la descarga…")
        self._log("Se solicitó cancelar la descarga.")
        self._engine.cancel()

    def _consume_events(self) -> None:
        for _ in range(150):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
            if self._close_when_done and not self._running:
                self.destroy()
                return
        self.after(80, self._consume_events)

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        message = str(event.get("message") or "")
        if event_type == "status":
            if message:
                self._log(message)
                if not self._cancel_requested:
                    self._set_status(message)
        elif event_type == "progress":
            try:
                percent = max(0.0, min(100.0, float(event.get("percent", 0))))
            except (TypeError, ValueError):
                return
            self.progress_bar.set(percent / 100)
            self._update_progress_label(percent)
        elif event_type == "file":
            path = event.get("path")
            if path:
                self._add_file(Path(path))
                self._completed += 1
                self._update_progress_label()
                self._log(f"Guardado: {Path(path).name}")
        elif event_type == "error":
            self._errors += 1
            self._set_status(message or "No se pudo descargar este enlace.", error=True)
            self._log(message or "Error de descarga.")
        elif event_type == "done":
            self._completed = int(event.get("completed", self._completed))
            self._total = int(event.get("total", self._total))
            self._errors = int(event.get("failed", self._errors))
            self._cancel_requested = bool(event.get("cancelled", self._cancel_requested))
            self._set_running(False)
            self.cancel_button.configure(text="Cancelar")
            self._engine = None
            if self._cancel_requested:
                summary = f"Descarga cancelada. {self._completed} archivo(s) guardado(s)."
            elif self._errors:
                summary = f"Proceso terminado: {self._completed} archivo(s), {self._errors} error(es)."
            else:
                summary = message or f"Listo. {self._completed} archivo(s) guardado(s)."
                self.progress_bar.set(1)
            self._set_status(summary, error=bool(self._errors))
            self._update_progress_label()
            self._log(summary)

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status_label.configure(
            text=message,
            text_color=COLORS["error"] if error else COLORS["muted"],
        )

    def _update_progress_label(self, percent: float | None = None) -> None:
        label = f"{self._completed} de {self._total} enlace(s) guardado(s)"
        if percent is not None:
            label += f"  ·  {percent:.0f}% del proceso"
        self.progress_label.configure(text=label)

    def _log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{datetime.now():%H:%M:%S}  {message}\n")
        self._log_lines += message.count("\n") + 1
        if self._log_lines > 700:
            self.log_box.delete("1.0", "101.0")
            self._log_lines -= 100
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _add_file(self, path: Path) -> None:
        absolute_path = path.expanduser().resolve()
        if str(absolute_path) in self._known_files:
            return
        if not self._known_files:
            self.empty_files_label.destroy()
        self._known_files.add(str(absolute_path))
        row = ctk.CTkFrame(self.files_list, fg_color="transparent")
        row.grid(row=len(self._known_files) - 1, column=0, sticky="ew", pady=(0, 10))
        row.grid_columnconfigure(0, weight=1)
        self._label(row, absolute_path.name, size=13, anchor="w", justify="left", wraplength=260).grid(
            row=0, column=0, sticky="ew", padx=(5, 4)
        )
        ctk.CTkButton(
            row,
            text="Mostrar",
            width=70,
            height=28,
            fg_color=COLORS["border"],
            hover_color="#354A62",
            command=lambda saved_path=absolute_path: self._show_file(saved_path),
        ).grid(row=1, column=0, sticky="w", padx=5, pady=(5, 0))

    def _open_output_directory(self) -> None:
        path = Path(self.output_directory.get()).expanduser()
        if not path.is_dir():
            self._set_status("La carpeta de salida se creará al iniciar la descarga.")
            return
        self._open_path(path)

    def _show_file(self, path: Path) -> None:
        if not path.is_file():
            self._set_status("El archivo ya no está en esa carpeta.", error=True)
            return
        if platform.system() == "Darwin":
            self._launch_opener(["open", "-R", str(path)])
        else:
            self._open_path(path.parent)

    def _open_path(self, path: Path) -> None:
        system = platform.system()
        if system == "Darwin":
            self._launch_opener(["open", str(path)])
        elif system == "Windows":
            try:
                os.startfile(str(path))
            except OSError as exc:
                self._set_status(f"No se pudo abrir la carpeta: {exc}", error=True)
        else:
            self._launch_opener(["xdg-open", str(path)])

    def _launch_opener(self, arguments: list[str]) -> None:
        try:
            subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            self._set_status(f"No se pudo abrir la carpeta: {exc}", error=True)

    def _on_close(self) -> None:
        if self._running:
            self._close_when_done = True
            self._cancel_download()
            self._set_status("Cerrando AudioLocal: finalizando la descarga…")
        else:
            self.destroy()


def main() -> None:
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    AudioLocalApp().mainloop()


if __name__ == "__main__":
    main()
