#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NV Band Preference Center – 3G / 4G Edition

Supported NV items
------------------
NV#6828  : LTE Band Preference
             One Uint64 field, LTE Band 1-64

NV#1877  : WCDMA Band Preference
             One Uint64 field, WCDMA Band 1-64

NV#4548  : WCDMA/GSM Band Preference
             One Uint64 field, WCDMA/GSM Band 1-64

Mapping rule
------------
Local Bit is 1-based.
Bit value = 2^(Local Bit - 1)

Example:
Band 1  -> bits_1_64   -> Local Bit 1  -> 2^0  = 1
Band 8  -> bits_1_64   -> Local Bit 8  -> 2^7  = 128
Band 20 -> bits_1_64   -> Local Bit 20 -> 2^19 = 524288
Total = 524417 (0x0000000000080101)
"""

from __future__ import annotations

import csv
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Iterable

APP_TITLE = "NV Band Preference Center – 3G/4G"
APP_VERSION = "v1.0"

GROUP_SIZE = 64
GROUP_COUNT = 5
MAX_UINT64 = (1 << 64) - 1

BG = "#070A0F"
SIDEBAR = "#0D121A"
PANEL = "#111823"
PANEL_2 = "#161F2B"
ENTRY = "#080C12"
GRID = "#2A3543"
FG = "#F2F6FA"
MUTED = "#96A4B5"
RED = "#FF3150"
CYAN = "#00BCEF"
PURPLE = "#9D6CFF"
GREEN = "#45D69A"
ORANGE = "#FFB75E"


@dataclass(frozen=True)
class NVDefinition:
    nv_id: int
    description: str
    full_name: str
    category: str
    display_name: str
    field_count: int
    max_band: int
    accent: str
    default_bands: str

    @property
    def type_text(self) -> str:
        return "Uint64" if self.field_count == 1 else f"Uint64 x {self.field_count}"

    @property
    def size_text(self) -> str:
        return "64" if self.field_count == 1 else "64 per row"


NV_ITEMS = {
    6828: NVDefinition(
        nv_id=6828,
        description="LTE Band Preference",
        full_name="/nv/item_files/modem/mmode/lte_band_pref",
        category="MMode",
        display_name="LTE Band Pref",
        field_count=1,
        max_band=64,
        accent=GREEN,
        default_bands="1, 3, 7, 8, 20, 28, 38",
    ),
    1877: NVDefinition(
        nv_id=1877,
        description="WCDMA Band Preference",
        full_name="/nv/item_files/modem/mmode/wcdma_band_pref",
        category="MMode",
        display_name="WCDMA Band Pref",
        field_count=1,
        max_band=64,
        accent=ORANGE,
        default_bands="1, 2, 5, 8",
    ),
    4548: NVDefinition(
        nv_id=4548,
        description="WCDMA/GSM Band Preference",
        full_name="/nv/item_files/modem/mmode/wcdma_gsm_band_pref",
        category="MMode",
        display_name="WCDMA/GSM Band Pref",
        field_count=1,
        max_band=64,
        accent=CYAN,
        default_bands="1, 2, 5, 8",
    ),
}


def field_name(index: int) -> str:
    start = index * GROUP_SIZE + 1
    end = start + GROUP_SIZE - 1
    return f"bits_{start}_{end}"


def band_range(index: int) -> str:
    start = index * GROUP_SIZE + 1
    end = start + GROUP_SIZE - 1
    return f"Band {start}-{end}"


def parse_integer(text: str) -> int:
    cleaned = text.strip().replace(",", "").replace("_", "").replace(" ", "")
    if not cleaned:
        return 0

    try:
        value = int(cleaned, 0)
    except ValueError:
        try:
            value = int(cleaned, 10)
        except ValueError as exc:
            raise ValueError(f"Invalid Uint64 value: {text}") from exc

    if not 0 <= value <= MAX_UINT64:
        raise ValueError(f"Value must be between 0 and {MAX_UINT64:,}.")
    return value


def parse_bands(text: str, max_band: int) -> list[int]:
    text = text.strip()
    if not text:
        return []

    cleaned = text.replace("，", ",").replace("；", ";")
    cleaned = re.sub(r"(?i)\b(?:band|lte|nr|wcdma|gsm)\s*", "", cleaned)
    cleaned = re.sub(r"(?i)\b[bn](?=\d)", "", cleaned)

    tokens = [token for token in re.split(r"[,;\s]+", cleaned) if token]
    bands: set[int] = set()

    for token in tokens:
        token = token.strip()
        if any(separator in token for separator in ("-", "–", "~")):
            parts = re.split(r"[-–~]", token, maxsplit=1)
            if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
                raise ValueError(f"Invalid band range: {token}")
            start, end = (int(part.strip()) for part in parts)
            if start > end:
                start, end = end, start
            bands.update(range(start, end + 1))
        else:
            if not token.isdigit():
                raise ValueError(f"Invalid band: {token}")
            bands.add(int(token))

    invalid = sorted(band for band in bands if not 1 <= band <= max_band)
    if invalid:
        raise ValueError(
            f"This NV supports Band 1-{max_band}.\n"
            f"Invalid value(s): {', '.join(map(str, invalid))}"
        )

    return sorted(bands)


def encode_bands(bands: Iterable[int], field_count: int) -> list[int]:
    values = [0] * field_count

    for band in sorted(set(bands)):
        group_index = (band - 1) // GROUP_SIZE
        if group_index >= field_count:
            raise ValueError(f"Band {band} is outside the available NV fields.")
        local_bit = ((band - 1) % GROUP_SIZE) + 1
        values[group_index] |= 1 << (local_bit - 1)

    return values


def decode_values(values: Iterable[int]) -> list[int]:
    bands: list[int] = []
    for group_index, value in enumerate(values):
        for offset in range(GROUP_SIZE):
            if value & (1 << offset):
                bands.append(group_index * GROUP_SIZE + offset + 1)
    return bands


def compact_bands(bands: Iterable[int]) -> str:
    values = sorted(set(bands))
    if not values:
        return ""

    parts: list[str] = []
    start = previous = values[0]

    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value

    parts.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(parts)


def format_hex(value: int) -> str:
    return f"0x{value:016X}"


def format_binary(value: int) -> str:
    raw = f"{value:064b}"
    return " ".join(raw[index:index + 8] for index in range(0, 64, 8))


def mapping_detail(bands: Iterable[int]) -> list[tuple[int, str, int, int, int]]:
    rows: list[tuple[int, str, int, int, int]] = []
    for band in sorted(set(bands)):
        index = (band - 1) // GROUP_SIZE
        local_bit = ((band - 1) % GROUP_SIZE) + 1
        exponent = local_bit - 1
        rows.append((band, field_name(index), local_bit, exponent, 1 << exponent))
    return rows


class AccentFrame(tk.Frame):
    def __init__(self, parent: tk.Misc, accent: str) -> None:
        super().__init__(parent, bg=accent, bd=0, highlightthickness=0)
        self.body = tk.Frame(self, bg=PANEL, bd=0, highlightthickness=0)
        self.body.pack(fill="both", expand=True, padx=3, pady=3)


class NVPage(tk.Frame):
    def __init__(self, parent: tk.Misc, definition: NVDefinition, status_callback) -> None:
        super().__init__(parent, bg=BG)
        self.definition = definition
        self.status_callback = status_callback

        self.band_var = tk.StringVar(value=definition.default_bands)
        self.value_vars = [tk.StringVar(value="0") for _ in range(definition.field_count)]
        self.decoded_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="")

        self.hex_labels: list[tk.Label] = []
        self.band_labels: list[tk.Label] = []

        self._build()
        self.calculate()

    def _entry(self, parent: tk.Misc, variable: tk.StringVar, readonly: bool = False) -> tk.Entry:
        options = {
            "textvariable": variable,
            "bg": ENTRY,
            "fg": GREEN if readonly else FG,
            "insertbackground": FG,
            "relief": "flat",
            "highlightthickness": 1,
            "highlightbackground": GRID,
            "highlightcolor": self.definition.accent,
            "font": ("Consolas", 10),
        }
        if readonly:
            options.update({"state": "readonly", "readonlybackground": ENTRY})
        return tk.Entry(parent, **options)

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(0, 10))

        tk.Label(
            header,
            text=f"NV#{self.definition.nv_id}",
            bg=BG,
            fg=self.definition.accent,
            font=("Segoe UI", 22, "bold"),
        ).pack(side="left")

        tk.Label(
            header,
            text=self.definition.description,
            bg=BG,
            fg=FG,
            font=("Segoe UI", 15, "bold"),
        ).pack(side="left", padx=(12, 0), pady=(5, 0))

        meta = AccentFrame(self, self.definition.accent)
        meta.pack(fill="x", pady=(0, 10))

        meta_grid = tk.Frame(meta.body, bg=PANEL)
        meta_grid.pack(fill="x", padx=12, pady=10)

        metadata = [
            ("NVITEM ID", str(self.definition.nv_id)),
            ("DESCRIPTION", self.definition.description),
            ("FULL NAME", self.definition.full_name),
            ("CATEGORY", self.definition.category),
            ("NAME", self.definition.display_name),
            ("SIZE", self.definition.size_text),
            ("TYPE", self.definition.type_text),
        ]

        for index, (name, value) in enumerate(metadata):
            row = index // 4
            column = index % 4
            cell = tk.Frame(meta_grid, bg=PANEL_2)
            cell.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 5, 0),
                pady=(0 if row == 0 else 5, 0),
            )
            tk.Label(
                cell,
                text=name,
                bg=PANEL_2,
                fg=MUTED,
                anchor="w",
                padx=8,
                pady=0,
                font=("Segoe UI", 8, "bold"),
            ).pack(fill="x", pady=(6, 1))
            tk.Label(
                cell,
                text=value,
                bg=PANEL_2,
                fg=FG,
                anchor="w",
                padx=8,
                pady=0,
                font=("Consolas", 9),
            ).pack(fill="x", pady=(1, 7))

        for column in range(4):
            meta_grid.grid_columnconfigure(column, weight=1)

        input_panel = tk.Frame(self, bg=PANEL)
        input_panel.pack(fill="x", pady=(0, 10))

        input_row = tk.Frame(input_panel, bg=PANEL)
        input_row.pack(fill="x", padx=12, pady=10)

        tk.Label(
            input_row,
            text="Supported Bands",
            bg=PANEL,
            fg=FG,
            width=18,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")

        band_entry = self._entry(input_row, self.band_var)
        band_entry.pack(side="left", fill="x", expand=True, ipady=7)
        band_entry.bind("<Return>", lambda _event: self.calculate())

        ttk.Button(
            input_row,
            text="Band -> NV",
            style="Primary.TButton",
            command=self.calculate,
        ).pack(side="left", padx=(9, 5))

        ttk.Button(
            input_row,
            text="NV -> Band",
            style="Dark.TButton",
            command=self.decode,
        ).pack(side="left", padx=5)

        ttk.Button(
            input_row,
            text="Copy PCAT",
            style="Dark.TButton",
            command=self.copy_pcat,
        ).pack(side="left", padx=5)

        ttk.Button(
            input_row,
            text="Export CSV",
            style="Dark.TButton",
            command=self.export_csv,
        ).pack(side="left", padx=(5, 0))

        table = tk.Frame(self, bg=GRID)
        table.pack(fill="x", pady=(0, 10))

        headers = ("INPUT Field", "Band Range", "Decimal / HEX Input", "PCAT HEX", "Enabled Bands")
        widths = (17, 15, 29, 22, 33)

        for column, (text, width) in enumerate(zip(headers, widths)):
            tk.Label(
                table,
                text=text,
                width=width,
                bg=PANEL_2,
                fg=FG,
                anchor="w",
                padx=7,
                pady=5,
                font=("Segoe UI", 9, "bold"),
            ).grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 1, 0),
            )

        for row in range(self.definition.field_count):
            input_name = self.definition.display_name if self.definition.field_count == 1 else field_name(row)

            tk.Label(
                table,
                text=input_name,
                bg=PANEL,
                fg=FG,
                anchor="w",
                padx=7,
                pady=5,
                font=("Consolas", 9),
            ).grid(row=row + 1, column=0, sticky="nsew", pady=(1, 0))

            range_text = "Band 1-64" if self.definition.field_count == 1 else band_range(row)
            tk.Label(
                table,
                text=range_text,
                bg=PANEL,
                fg=MUTED,
                anchor="w",
                padx=7,
                pady=5,
                font=("Segoe UI", 9),
            ).grid(row=row + 1, column=1, sticky="nsew", padx=(1, 0), pady=(1, 0))

            entry = self._entry(table, self.value_vars[row])
            entry.grid(
                row=row + 1,
                column=2,
                sticky="nsew",
                padx=(1, 0),
                pady=(1, 0),
                ipady=4,
            )
            entry.bind("<Return>", lambda _event: self.decode())

            hex_label = tk.Label(
                table,
                text="0x0000000000000000",
                bg=PANEL,
                fg=ORANGE,
                anchor="e",
                padx=7,
                pady=5,
                font=("Consolas", 9),
            )
            hex_label.grid(row=row + 1, column=3, sticky="nsew", padx=(1, 0), pady=(1, 0))
            self.hex_labels.append(hex_label)

            band_label = tk.Label(
                table,
                text="-",
                bg=PANEL,
                fg=FG,
                anchor="w",
                padx=7,
                pady=5,
                font=("Consolas", 9),
            )
            band_label.grid(row=row + 1, column=4, sticky="nsew", padx=(1, 0), pady=(1, 0))
            self.band_labels.append(band_label)

        table.grid_columnconfigure(2, weight=1)
        table.grid_columnconfigure(4, weight=2)

        detail_container = tk.Frame(self, bg=BG)
        detail_container.pack(fill="both", expand=True)
        detail_container.grid_columnconfigure(0, weight=2)
        detail_container.grid_columnconfigure(1, weight=1)
        detail_container.grid_rowconfigure(0, weight=1)

        detail_panel = tk.Frame(detail_container, bg=PANEL)
        detail_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        tk.Label(
            detail_panel,
            text="Calculation Detail",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            padx=10,
            pady=7,
            font=("Segoe UI", 9, "bold"),
        ).pack(fill="x")

        self.detail_text = ScrolledText(
            detail_panel,
            bg=ENTRY,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=GRID,
            font=("Consolas", 9),
            wrap="none",
            height=10,
        )
        self.detail_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.detail_text.configure(state="disabled")

        summary_panel = tk.Frame(detail_container, bg=PANEL)
        summary_panel.grid(row=0, column=1, sticky="nsew")

        tk.Label(
            summary_panel,
            text="PCAT Summary",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            padx=10,
            pady=7,
            font=("Segoe UI", 9, "bold"),
        ).pack(fill="x")

        self.summary_text = ScrolledText(
            summary_panel,
            bg=ENTRY,
            fg=GREEN,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=GRID,
            font=("Consolas", 9),
            wrap="word",
            height=10,
        )
        self.summary_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.summary_text.configure(state="disabled")

    def _set_text(self, widget: ScrolledText, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _update_display(self, values: list[int], bands: list[int]) -> None:
        grouped: list[list[int]] = [[] for _ in range(self.definition.field_count)]
        for band in bands:
            grouped[(band - 1) // GROUP_SIZE].append(band)

        for index, value in enumerate(values):
            self.value_vars[index].set(str(value))
            self.hex_labels[index].configure(text=format_hex(value))
            self.band_labels[index].configure(
                text=compact_bands(grouped[index]) if grouped[index] else "-"
            )

        rows = mapping_detail(bands)
        if rows:
            lines = [
                f"Band {band:>3} -> {field:<13} Local Bit {local_bit:>2} "
                f"-> 2^{exponent:<2} = {bit_value:,} ({format_hex(bit_value)})"
                for band, field, local_bit, exponent, bit_value in rows
            ]
        else:
            lines = ["No enabled band."]

        self._set_text(self.detail_text, "\n".join(lines))

        pcat_lines = [
            f"NVITEM ID  : {self.definition.nv_id}",
            f"DESCRIPTION: {self.definition.description}",
            f"FULL NAME  : {self.definition.full_name}",
            f"NAME       : {self.definition.display_name}",
            f"TYPE       : {self.definition.type_text}",
            "",
        ]
        for index, value in enumerate(values):
            input_name = self.definition.display_name if self.definition.field_count == 1 else field_name(index)
            pcat_lines.append(f"{input_name} = {format_hex(value)}")
        pcat_lines.extend(["", f"Supported Bands: {', '.join(map(str, bands)) or 'None'}"])
        self._set_text(self.summary_text, "\n".join(pcat_lines))

        self.decoded_var.set(", ".join(map(str, bands)))

    def calculate(self) -> None:
        try:
            bands = parse_bands(self.band_var.get(), self.definition.max_band)
            values = encode_bands(bands, self.definition.field_count)
            self._update_display(values, bands)
            self.status_callback(
                f"NV#{self.definition.nv_id}: calculated {len(bands)} band(s)."
            )
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc), parent=self)
            self.status_callback(f"NV#{self.definition.nv_id}: calculation failed.")

    def decode(self) -> None:
        try:
            values = [parse_integer(variable.get()) for variable in self.value_vars]
            bands = decode_values(values)
            bands = [band for band in bands if band <= self.definition.max_band]
            self.band_var.set(", ".join(map(str, bands)))
            self._update_display(values, bands)
            self.status_callback(
                f"NV#{self.definition.nv_id}: decoded {len(bands)} band(s)."
            )
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc), parent=self)
            self.status_callback(f"NV#{self.definition.nv_id}: decode failed.")

    def copy_pcat(self) -> None:
        text = self.summary_text.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.status_callback(f"NV#{self.definition.nv_id}: PCAT values copied.")

    def export_csv(self) -> None:
        try:
            bands = parse_bands(self.band_var.get(), self.definition.max_band)
            values = [parse_integer(variable.get()) for variable in self.value_vars]
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc), parent=self)
            return

        output_path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Export NV#{self.definition.nv_id}",
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv"), ("All files", "*.*")],
            initialfile=f"NV_{self.definition.nv_id}_band_preference.csv",
        )
        if not output_path:
            return

        with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["NVITEM ID", self.definition.nv_id])
            writer.writerow(["DESCRIPTION", self.definition.description])
            writer.writerow(["FULL NAME", self.definition.full_name])
            writer.writerow(["NAME", self.definition.display_name])
            writer.writerow(["CATEGORY", self.definition.category])
            writer.writerow(["TYPE", self.definition.type_text])
            writer.writerow([])
            writer.writerow(["INPUT Field", "Band Range", "Decimal", "HEX", "Enabled Bands"])

            grouped: list[list[int]] = [[] for _ in range(self.definition.field_count)]
            for band in bands:
                grouped[(band - 1) // GROUP_SIZE].append(band)

            for index, value in enumerate(values):
                input_name = self.definition.display_name if self.definition.field_count == 1 else field_name(index)
                range_text = "Band 1-64" if self.definition.field_count == 1 else band_range(index)
                writer.writerow(
                    [
                        input_name,
                        range_text,
                        value,
                        format_hex(value),
                        ", ".join(map(str, grouped[index])),
                    ]
                )

            writer.writerow([])
            writer.writerow(["Band", "Field", "Local Bit", "Formula", "Bit Value", "Bit HEX"])
            for band, field, local_bit, exponent, bit_value in mapping_detail(bands):
                writer.writerow(
                    [band, field, local_bit, f"2^{exponent}", bit_value, format_hex(bit_value)]
                )

        self.status_callback(f"CSV exported: {Path(output_path).name}")


class OverviewPage(tk.Frame):
    """
    Dashboard quick calculators for 3G / 4G NV items.

    All three NV items (NV#6828, NV#1877, NV#4548) use a single Uint64,
    so each quick card follows the same single-field layout.
    """

    def __init__(self, parent: tk.Misc, open_callback, status_callback) -> None:
        super().__init__(parent, bg=BG)
        self.open_callback = open_callback
        self.status_callback = status_callback

        # 每個 NV 的快速計算變數
        self.quick_vars: dict[int, dict] = {}
        for nv_id, definition in NV_ITEMS.items():
            self.quick_vars[nv_id] = {
                "value": tk.StringVar(value="0"),
                "bands": tk.StringVar(value=definition.default_bands),
                "decimal": tk.StringVar(value="DEC: 0"),
            }

        self._build()
        # 初始化時對每個 NV 做 decode
        for nv_id in NV_ITEMS:
            self.decode_quick_value(nv_id, show_error=False)

    def _dark_entry(
        self,
        parent: tk.Misc,
        variable: tk.StringVar,
        *,
        font_size: int = 10,
        accent: str = GREEN,
    ) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            bg=ENTRY,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=GRID,
            highlightcolor=accent,
            font=("Consolas", font_size),
        )

    def _build(self) -> None:
        hero = tk.Frame(self, bg=BG)
        hero.pack(fill="x", pady=(1, 10))

        tk.Label(
            hero,
            text="NV Band Preference Center – 3G/4G",
            bg=BG,
            fg=FG,
            font=("Segoe UI", 23, "bold"),
        ).pack(anchor="w")

        tk.Label(
            hero,
            text=(
                "Quick calculation on one page: NV#6828 (LTE), NV#1877 (WCDMA), "
                "and NV#4548 (WCDMA/GSM) each use one Uint64 field."
            ),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        cards = tk.Frame(self, bg=BG)
        cards.pack(fill="x")

        for column in range(len(NV_ITEMS)):
            cards.grid_columnconfigure(column, weight=1, uniform="card")
        cards.grid_rowconfigure(0, weight=1)

        for column, (nv_id, definition) in enumerate(NV_ITEMS.items()):
            self._build_quick_card(cards, definition, column)

        rule = tk.Frame(self, bg=PANEL)
        rule.pack(fill="both", expand=True, pady=(10, 0))

        tk.Label(
            rule,
            text="Calculation Rule",
            bg=PANEL,
            fg=FG,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 2))

        tk.Label(
            rule,
            text=(
                "Local Bit is 1-based. Value = 2^(Local Bit - 1).\n"
                "Band 1  -> bits_1_64 -> Local Bit 1  -> 2^0  = 1       |    "
                "Band 8  -> bits_1_64 -> Local Bit 8  -> 2^7  = 128     |    "
                "Band 20 -> bits_1_64 -> Local Bit 20 -> 2^19 = 524288"
            ),
            bg=PANEL,
            fg=GREEN,
            justify="left",
            font=("Consolas", 9),
        ).pack(anchor="w", padx=14, pady=(3, 11))

    def _build_quick_card(self, parent: tk.Misc, definition: NVDefinition, column: int) -> None:
        nv_id = definition.nv_id
        accent = definition.accent
        vars_ = self.quick_vars[nv_id]

        border = tk.Frame(parent, bg=accent)
        border.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 7, 0),
        )

        card = tk.Frame(border, bg=PANEL)
        card.pack(fill="both", expand=True, padx=3, pady=3)

        tk.Label(
            card,
            text=f"NV#{nv_id}",
            bg=PANEL,
            fg=accent,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 0))

        tk.Label(
            card,
            text=definition.description,
            bg=PANEL,
            fg=FG,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=12, pady=(1, 0))

        tk.Label(
            card,
            text=definition.full_name,
            bg=PANEL,
            fg=MUTED,
            wraplength=330,
            justify="left",
            font=("Consolas", 7),
        ).pack(anchor="w", padx=12, pady=(5, 3))

        tk.Label(
            card,
            text="NV Value",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", padx=12, pady=(8, 2))

        value_entry = self._dark_entry(card, vars_["value"], font_size=9, accent=accent)
        value_entry.pack(fill="x", padx=12, ipady=5)
        value_entry.bind("<Return>", lambda _event, nid=nv_id: self.decode_quick_value(nid))

        info_row = tk.Frame(card, bg=PANEL)
        info_row.pack(fill="x", padx=12, pady=(6, 4))

        for text, fg in (
            ("HEX / DEC", ORANGE),
            ("Uint64", FG),
            ("Size 64", FG),
        ):
            tk.Label(
                info_row,
                text=text,
                bg=PANEL_2,
                fg=fg,
                padx=6,
                pady=3,
                font=("Segoe UI", 7, "bold"),
            ).pack(side="left", padx=(0, 4))

        tk.Label(
            info_row,
            text=f"Band 1-{definition.max_band}",
            bg=PANEL_2,
            fg=FG,
            padx=6,
            pady=3,
            font=("Segoe UI", 7),
        ).pack(side="right")

        tk.Label(
            card,
            textvariable=vars_["decimal"],
            bg=PANEL,
            fg=GREEN,
            font=("Consolas", 8),
        ).pack(anchor="w", padx=12, pady=(0, 3))

        tk.Label(
            card,
            text="Supported Bands",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", padx=12, pady=(2, 2))

        bands_entry = self._dark_entry(card, vars_["bands"], font_size=9, accent=accent)
        bands_entry.pack(fill="x", padx=12, ipady=5)
        bands_entry.bind(
            "<Return>", lambda _event, nid=nv_id: self.calculate_quick_value(nid)
        )

        action_row = tk.Frame(card, bg=PANEL)
        action_row.pack(fill="x", padx=12, pady=(8, 10))

        ttk.Button(
            action_row,
            text="Decode",
            style="Dark.TButton",
            command=lambda nid=nv_id: self.decode_quick_value(nid),
        ).pack(side="left")

        ttk.Button(
            action_row,
            text="Calculate",
            style="Dark.TButton",
            command=lambda nid=nv_id: self.calculate_quick_value(nid),
        ).pack(side="left", padx=4)

        ttk.Button(
            action_row,
            text="Open",
            style="Dark.TButton",
            command=lambda nid=nv_id: self.open_callback(nid),
        ).pack(side="right")

    def decode_quick_value(self, nv_id: int, show_error: bool = True) -> None:
        definition = NV_ITEMS[nv_id]
        vars_ = self.quick_vars[nv_id]
        try:
            value = parse_integer(vars_["value"].get())
            bands = decode_values([value])
            vars_["value"].set(format_hex(value))
            vars_["bands"].set(", ".join(map(str, bands)))
            vars_["decimal"].set(f"DEC: {value:,}")
            self.status_callback(
                f"NV#{nv_id} quick decode: {len(bands)} supported band(s)."
            )
        except ValueError as exc:
            if show_error:
                messagebox.showerror(f"NV#{nv_id} Input Error", str(exc), parent=self)
            self.status_callback(f"NV#{nv_id} quick decode failed.")

    def calculate_quick_value(self, nv_id: int) -> None:
        definition = NV_ITEMS[nv_id]
        vars_ = self.quick_vars[nv_id]
        try:
            bands = parse_bands(vars_["bands"].get(), definition.max_band)
            value = encode_bands(bands, 1)[0]
            vars_["value"].set(format_hex(value))
            vars_["bands"].set(", ".join(map(str, bands)))
            vars_["decimal"].set(f"DEC: {value:,}")
            self.status_callback(
                f"NV#{nv_id} quick calculation: {len(bands)} supported band(s)."
            )
        except ValueError as exc:
            messagebox.showerror(f"NV#{nv_id} Band Error", str(exc), parent=self)
            self.status_callback(f"NV#{nv_id} quick calculation failed.")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1450x900")
        self.minsize(1240, 760)
        self.configure(bg=BG)

        self.status_var = tk.StringVar(value="Ready")
        self.pages: dict[str, tk.Frame] = {}
        self.nav_buttons: dict[str, tk.Button] = {}

        self._configure_style()
        self._build()
        self.show_page("Overview")

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Dark.TButton",
            background="#202B38",
            foreground=FG,
            bordercolor=GRID,
            padding=(11, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Dark.TButton",
            background=[("active", "#2E3B4B"), ("pressed", "#17202A")],
        )

        style.configure(
            "Primary.TButton",
            background="#2E3B4B",
            foreground=FG,
            bordercolor="#3D4C5D",
            padding=(12, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#3B4B5E"), ("pressed", "#1D2732")],
        )

    def _build(self) -> None:
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)

        sidebar = tk.Frame(shell, bg=SIDEBAR, width=225)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar,
            text="3G / 4G\nNV BAND\nPREFERENCE",
            bg=SIDEBAR,
            fg=FG,
            justify="left",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w", padx=18, pady=(20, 3))

        tk.Label(
            sidebar,
            text=APP_VERSION,
            bg=SIDEBAR,
            fg=MUTED,
            font=("Consolas", 9),
        ).pack(anchor="w", padx=18, pady=(0, 22))

        nav_items = [
            ("Overview", "Overview", MUTED),
            ("NV#6828", "6828", GREEN),
            ("NV#1877", "1877", ORANGE),
            ("NV#4548", "4548", CYAN),
        ]

        for label, key, accent in nav_items:
            button = tk.Button(
                sidebar,
                text=label,
                bg=SIDEBAR,
                fg=FG,
                activebackground=PANEL_2,
                activeforeground=FG,
                relief="flat",
                bd=0,
                anchor="w",
                padx=18,
                pady=11,
                font=("Segoe UI", 10, "bold"),
                command=lambda page_key=key: self.show_page(page_key),
            )
            button.pack(fill="x", pady=1)
            self.nav_buttons[key] = button

        tk.Frame(sidebar, bg=GRID, height=1).pack(fill="x", padx=18, pady=18)

        tk.Label(
            sidebar,
            text=(
                "NV#6828\n"
                "LTE Band Preference\n\n"
                "NV#1877\n"
                "WCDMA Band Preference\n\n"
                "NV#4548\n"
                "WCDMA/GSM Band Pref\n\n"
                "All single Uint64"
            ),
            bg=SIDEBAR,
            fg=MUTED,
            justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=18)

        main = tk.Frame(shell, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        topbar = tk.Frame(main, bg=PANEL, height=54)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(
            topbar,
            text="PCAT 3G/4G NV Band Preference Calculator",
            bg=PANEL,
            fg=FG,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=18, pady=16)

        tk.Label(
            topbar,
            text="Band -> Uint64 | Uint64 -> Band",
            bg=PANEL,
            fg=MUTED,
            font=("Consolas", 9),
        ).pack(side="right", padx=18, pady=16)

        content = tk.Frame(main, bg=BG)
        content.pack(fill="both", expand=True, padx=18, pady=16)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        overview = OverviewPage(content, self.open_nv, self.set_status)
        overview.grid(row=0, column=0, sticky="nsew")
        self.pages["Overview"] = overview

        for nv_id, definition in NV_ITEMS.items():
            page = NVPage(content, definition, self.set_status)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[str(nv_id)] = page

        statusbar = tk.Frame(main, bg=PANEL, height=30)
        statusbar.pack(fill="x")
        statusbar.pack_propagate(False)

        tk.Label(
            statusbar,
            textvariable=self.status_var,
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 8),
        ).pack(fill="x", padx=14, pady=7)

    def open_nv(self, nv_id: int) -> None:
        self.show_page(str(nv_id))

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def show_page(self, key: str) -> None:
        page = self.pages[key]
        page.tkraise()

        for nav_key, button in self.nav_buttons.items():
            if nav_key == key:
                accent = MUTED if key == "Overview" else NV_ITEMS[int(key)].accent
                button.configure(bg=PANEL_2, fg=accent)
            else:
                button.configure(bg=SIDEBAR, fg=FG)

        self.set_status(f"Opened {key}.")


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
