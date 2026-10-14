import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
import subprocess
import threading
import datetime
import os
from pathlib import Path
import re
import shutil

# --- 顏色與常數定義 ---
APP_TITLE = "iPerf3 Testing Center"
APP_VERSION = "v1.1"
BG = "#070A0F"
PANEL = "#111823"
PANEL_2 = "#161F2B"
ENTRY = "#080C12"
GRID = "#2A3543"
FG = "#F2F6FA"
MUTED = "#96A4B5"
RED = "#FF3150"
CYAN = "#00BCEF"
GREEN = "#45D69A"
ORANGE = "#FFB75E"

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "logs"


def _positive_integer(value, label, maximum=None):
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError(f"{label} must be a positive integer.")
    number = int(value)
    if number < 1 or (maximum is not None and number > maximum):
        limit = f" between 1 and {maximum}" if maximum is not None else " greater than 0"
        raise ValueError(f"{label} must be{limit}.")
    return str(number)


def build_iperf_command(mode, ip, port, protocol="TCP", duration="10", parallel="1",
                        bandwidth="", window="", reverse=False, executable="iperf3"):
    """Validate GUI values and build an argument list without starting a process."""
    if mode not in {"Server", "Client"}:
        raise ValueError("Mode must be Server or Client.")
    port = _positive_integer(port, "Port", 65535)
    ip = ip.strip()
    cmd = [str(executable), "-p", port, "-i", "1", "--forceflush"]
    if mode == "Server":
        cmd.append("-s")
        if ip:
            cmd.extend(["-B", ip])
        return cmd
    if not ip:
        raise ValueError("Target IP or hostname is required for Client mode.")
    if protocol not in {"TCP", "UDP"}:
        raise ValueError("Protocol must be TCP or UDP.")
    cmd.extend(["-c", ip])
    if protocol == "UDP":
        cmd.append("-u")
    if duration.strip():
        cmd.extend(["-t", _positive_integer(duration, "Duration")])
    if parallel.strip():
        streams = _positive_integer(parallel, "Parallel streams")
        if streams != "1":
            cmd.extend(["-P", streams])
    if bandwidth.strip():
        cmd.extend(["-b", bandwidth.strip()])
    if window.strip():
        cmd.extend(["-w", window.strip()])
    if reverse:
        cmd.append("-R")
    return cmd


def find_iperf_executable(script_dir=None):
    """Prefer an executable beside this script, then search the system PATH."""
    directory = Path(script_dir) if script_dir is not None else SCRIPT_DIR
    filename = "iperf3.exe" if os.name == "nt" else "iperf3"
    local = directory / filename
    if local.is_file():
        return str(local.resolve())
    executable = shutil.which("iperf3")
    if executable:
        return executable
    raise FileNotFoundError(f"{filename} not found. Place it beside this script or add it to PATH.")


def create_log_file(mode, port, cmd, log_dir=None, now=None):
    """Write the header before launch; exclusive creation prevents overwritten logs."""
    directory = Path(log_dir) if log_dir is not None else LOG_DIR
    directory.mkdir(parents=True, exist_ok=True)
    now = now or datetime.datetime.now()
    stem = f"{mode}_{now.strftime('%Y-%m-%d_%H_%M_%S_%f')}_port{port}"
    counter = 0
    while True:
        suffix = f"_{counter}" if counter else ""
        log_path = directory / f"{stem}{suffix}.txt"
        header = (
            "==========================================================\n"
            f"IPERF START TIME : {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"MODE : {mode}\n"
            f"COMMAND : {subprocess.list2cmdline(cmd)}\n"
            f"LOG FILE : {log_path.name}\n"
            "==========================================================\n\n"
        )
        try:
            with log_path.open("x", encoding="utf-8") as log:
                log.write(header)
            return str(log_path), header
        except FileExistsError:
            counter += 1


class IperfInstance(tk.Frame):
    """代表一個獨立執行的 iPerf3 任務分頁"""
    def __init__(self, parent, cmd, port, log_file, header_text):
        super().__init__(parent, bg=BG)
        self.cmd = cmd
        self.port = port
        self.log_file = log_file
        self.process = None
        self.is_running = False
        self.stop_requested = False
        
        self._build_ui()
        self.append_log(header_text)
        self.start_process()

    def _build_ui(self):
        header = tk.Frame(self, bg=PANEL)
        header.pack(fill="x", pady=(0, 5))
        
        self.lbl_status = tk.Label(header, text="Status: Starting...", bg=PANEL, fg=ORANGE, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(side="left", padx=10, pady=5)
        
        tk.Label(header, text=f"Log: {os.path.basename(self.log_file)}", bg=PANEL, fg=MUTED, font=("Consolas", 9)).pack(side="left", padx=10)
        
        self.btn_stop = ttk.Button(header, text="Stop Task", style="Danger.TButton", command=self.stop_process)
        self.btn_stop.pack(side="right", padx=10, pady=5)

        self.txt_console = ScrolledText(
            self, bg=ENTRY, fg=FG, insertbackground=FG,
            relief="flat", highlightthickness=1, highlightbackground=GRID,
            font=("Consolas", 9), wrap="word"
        )
        self.txt_console.pack(fill="both", expand=True, padx=5, pady=5)
        self.txt_console.bind("<Key>", lambda e: "break")

    def append_log(self, text):
        self.txt_console.insert(tk.END, text)
        self.txt_console.see(tk.END)

    def start_process(self):
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                startupinfo=startupinfo
            )
            self.is_running = True
            self.lbl_status.config(text="Status: RUNNING", fg=GREEN)
            threading.Thread(target=self._read_output, daemon=True).start()
            
        except OSError as exc:
            self._append_event(f"[ERROR] Could not start iPerf3: {exc}\n")
            self.lbl_status.config(text="Status: ERROR", fg=RED)
            self.btn_stop.config(state="disabled")
            self.is_running = False

    def _append_event(self, text):
        self.append_log(text)
        try:
            with open(self.log_file, 'a', encoding='utf-8') as log:
                log.write(text)
        except OSError as exc:
            self.append_log(f"[ERROR] Could not update log: {exc}\n")

    def _schedule_ui(self, callback, *args):
        try:
            self.after(0, callback, *args)
        except (RuntimeError, tk.TclError):
            # The window may already be closing while the reader finishes.
            pass

    def _read_output(self):
        read_error = None
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                for line in iter(self.process.stdout.readline, ''):
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    out_line = f"[{ts}] {line}"
                    f.write(out_line)
                    f.flush()
                    self._schedule_ui(self.append_log, out_line)
        except (OSError, UnicodeError) as exc:
            read_error = str(exc)
            if self.process.poll() is None:
                try:
                    self.process.terminate()
                except OSError:
                    pass
        finally:
            self.process.stdout.close()
        returncode = self.process.wait()
        self.is_running = False
        self._schedule_ui(self._finish_process, returncode, read_error)

    def _finish_process(self, returncode, read_error):
        if read_error:
            status, color = "ERROR", RED
        elif self.stop_requested:
            status, color = "STOPPED", ORANGE
        elif returncode == 0:
            status, color = "COMPLETED", GREEN
        else:
            status, color = "ERROR", RED
        self.lbl_status.config(text=f"Status: {status} (exit {returncode})", fg=color)
        if read_error:
            self._append_event(f"[ERROR] Could not read or save output: {read_error}\n")
        self._append_event(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] --- {status}; exit code {returncode} ---\n")
        self.btn_stop.config(state="disabled")

    def stop_process(self):
        if self.is_running and self.process:
            try:
                if self.process.poll() is None:
                    self.process.terminate()
                    self.stop_requested = True
            except OSError as exc:
                self._append_event(f"[ERROR] Could not stop iPerf3: {exc}\n")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1100x750")
        self.configure(bg=BG)
        self.instances = []

        self._configure_style()
        self._build_sidebar()
        self._build_main_area()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 初始化時觸發一次狀態切換，確保初始介面正確
        self._toggle_fields()

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
            
        style.configure("Primary.TButton", background="#2E3B4B", foreground=FG, bordercolor="#3D4C5D", padding=(10, 5), font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton", background=[("active", "#3B4B5E"), ("pressed", "#1D2732")])
        
        style.configure("Danger.TButton", background="#4A1520", foreground=RED, bordercolor="#5C1A27", padding=(10, 5), font=("Segoe UI", 9, "bold"))
        style.map("Danger.TButton", background=[("active", "#631C2A")])

        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL_2, foreground=FG, padding=(10, 5), font=("Segoe UI", 9))
        style.map("TNotebook.Tab", background=[("selected", CYAN)], foreground=[("selected", BG)])

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=PANEL, width=320)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="iPerf3 Config", bg=PANEL, fg=FG, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=15, pady=(20, 15))

        # --- 變數宣告 ---
        self.var_mode = tk.StringVar(value="Server")
        self.var_ip = tk.StringVar(value="")
        self.var_port = tk.StringVar(value="27008")
        
        # Client 專用變數
        self.var_proto = tk.StringVar(value="TCP")
        self.var_bw = tk.StringVar(value="")
        self.var_win = tk.StringVar(value="")
        self.var_time = tk.StringVar(value="10")      # -t 預設 10 秒
        self.var_parallel = tk.StringVar(value="1")   # -P 預設 1 條
        self.var_reverse = tk.BooleanVar(value=False) # -R 反向測試

        # --- 共用設定區 ---
        tk.Label(sidebar, text="[ General ]", bg=PANEL, fg=CYAN, font=("Consolas", 9, "bold")).pack(anchor="w", padx=15, pady=(5, 0))
        
        self._add_label(sidebar, "Mode:")
        self.cb_mode = ttk.Combobox(sidebar, textvariable=self.var_mode, values=["Server", "Client"], state="readonly", font=("Consolas", 10))
        self.cb_mode.pack(fill="x", padx=15, pady=(0, 10))
        self.cb_mode.bind("<<ComboboxSelected>>", self._toggle_fields) # 綁定切換事件
        
        self.lbl_ip = self._add_label(sidebar, "Bind IP (Optional):")
        tk.Entry(sidebar, textvariable=self.var_ip, bg=ENTRY, fg=FG, insertbackground=FG, font=("Consolas", 10)).pack(fill="x", padx=15, pady=(0, 10))

        self._add_label(sidebar, "Port:")
        tk.Entry(sidebar, textvariable=self.var_port, bg=ENTRY, fg=FG, insertbackground=FG, font=("Consolas", 10)).pack(fill="x", padx=15, pady=(0, 15))

        # --- Client 專用設定區 ---
        tk.Label(sidebar, text="[ Client Only ]", bg=PANEL, fg=CYAN, font=("Consolas", 9, "bold")).pack(anchor="w", padx=15, pady=(5, 0))

        self._add_label(sidebar, "Protocol:")
        self.cb_proto = ttk.Combobox(sidebar, textvariable=self.var_proto, values=["TCP", "UDP"], state="readonly", font=("Consolas", 10))
        self.cb_proto.pack(fill="x", padx=15, pady=(0, 10))

        # 使用 Frame 將進階參數排成雙欄以節省空間
        row1 = tk.Frame(sidebar, bg=PANEL)
        row1.pack(fill="x", padx=15, pady=(0, 10))
        
        frame_time = tk.Frame(row1, bg=PANEL)
        frame_time.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._add_label(frame_time, "Duration (-t):")
        self.ent_time = tk.Entry(frame_time, textvariable=self.var_time, bg=ENTRY, fg=FG, insertbackground=FG, font=("Consolas", 10))
        self.ent_time.pack(fill="x")

        frame_parallel = tk.Frame(row1, bg=PANEL)
        frame_parallel.pack(side="right", fill="x", expand=True, padx=(5, 0))
        self._add_label(frame_parallel, "Parallel (-P):")
        self.ent_parallel = tk.Entry(frame_parallel, textvariable=self.var_parallel, bg=ENTRY, fg=FG, insertbackground=FG, font=("Consolas", 10))
        self.ent_parallel.pack(fill="x")

        self._add_label(sidebar, "Bandwidth (e.g. 100M):")
        self.ent_bw = tk.Entry(sidebar, textvariable=self.var_bw, bg=ENTRY, fg=FG, insertbackground=FG, font=("Consolas", 10))
        self.ent_bw.pack(fill="x", padx=15, pady=(0, 10))

        self._add_label(sidebar, "Window Size (e.g. 64K):")
        self.ent_win = tk.Entry(sidebar, textvariable=self.var_win, bg=ENTRY, fg=FG, insertbackground=FG, font=("Consolas", 10))
        self.ent_win.pack(fill="x", padx=15, pady=(0, 10))

        self.chk_reverse = tk.Checkbutton(
            sidebar, text="Reverse Mode (-R)", variable=self.var_reverse,
            bg=PANEL, fg=MUTED, selectcolor=ENTRY, activebackground=PANEL, activeforeground=FG,
            font=("Segoe UI", 9, "bold")
        )
        self.chk_reverse.pack(anchor="w", padx=12, pady=(0, 20))

        # Start Button
        ttk.Button(sidebar, text="START TEST ▶", style="Primary.TButton", command=self.start_new_task).pack(fill="x", padx=15, pady=5)

    def _add_label(self, parent, text):
        lbl = tk.Label(parent, text=text, bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"))
        lbl.pack(anchor="w", pady=(5, 2))
        return lbl

    def _toggle_fields(self, event=None):
        """動態控制：當切換 Mode 時，啟用或禁用 Client 專屬欄位"""
        is_client = (self.var_mode.get() == "Client")
        state = "normal" if is_client else "disabled"
        cb_state = "readonly" if is_client else "disabled"
        bg_color = ENTRY if is_client else GRID
        fg_color = FG if is_client else MUTED

        # 更新 IP 標籤提示
        self.lbl_ip.config(text="Target IP (Required):" if is_client else "Bind IP (Optional):")

        # 更新元件狀態與顏色，呈現反灰效果
        self.cb_proto.config(state=cb_state)
        self.ent_time.config(state=state, disabledbackground=GRID, disabledforeground=MUTED)
        self.ent_parallel.config(state=state, disabledbackground=GRID, disabledforeground=MUTED)
        self.ent_bw.config(state=state, disabledbackground=GRID, disabledforeground=MUTED)
        self.ent_win.config(state=state, disabledbackground=GRID, disabledforeground=MUTED)
        self.chk_reverse.config(state=state, fg=fg_color)

    def _build_main_area(self):
        main_frame = tk.Frame(self, bg=BG)
        main_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)

    def start_new_task(self):
        mode = self.var_mode.get()
        ip = self.var_ip.get().strip()
        port = self.var_port.get().strip()

        try:
            cmd = build_iperf_command(
                mode, ip, port, self.var_proto.get(), self.var_time.get(),
                self.var_parallel.get(), self.var_bw.get(), self.var_win.get(),
                self.var_reverse.get(),
            )
            cmd[0] = find_iperf_executable()
            port = cmd[2]
            log_path, header_text = create_log_file(mode, port, cmd)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Error", str(exc))
            return

        task_frame = IperfInstance(self.notebook, cmd, port, log_path, header_text)
        tab_name = f"Port: {port} {'(Client)' if mode == 'Client' else '(Server)'}"
        self.notebook.add(task_frame, text=tab_name)
        self.notebook.select(task_frame)
        self.instances.append(task_frame)
        
    def on_closing(self):
        for instance in self.instances:
            instance.stop_process()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
