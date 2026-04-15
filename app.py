"""Textual TUI entry point for SPICE discontinuity tooling."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, Static

from spice_discontinuity.find import analyze_csv_discontinuities
from spice_discontinuity.generate import FetSpec, generate_fet_netlist
from spice_discontinuity.inject import inject_random_spikes

ALLOWED_FILE_EXTENSIONS = {".raw", ".csv", ".txt"}


def list_supported_files(directory: Path) -> list[Path]:
    """Return files in a directory that are selectable by the TUI."""
    return sorted(
        [
            path
            for path in directory.iterdir()
            if path.is_file()
            and not path.name.startswith(".")
            and path.suffix.lower() in ALLOWED_FILE_EXTENSIONS
        ],
        key=lambda item: item.name.lower(),
    )


class SpiceToolkitApp(App[None]):
    """A small command-driven TUI for the SPICE toolkit."""

    TITLE = "SPICE Discontinuity Toolkit"
    SUB_TITLE = "Commands: help, ls, find <index> [threshold], generate, inject, misc, quit"

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self._log_lines: list[str] = ["Type `help` for commands."]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static("", id="output")
            yield Input(placeholder="Enter command and press Enter...", id="command")
        yield Footer()

    def on_mount(self) -> None:
        self._write("Ready.")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command_line = event.value.strip()
        self.query_one("#command", Input).value = ""
        if not command_line:
            return
        self._write(f"> {command_line}")
        self._dispatch(command_line)

    def _dispatch(self, command_line: str) -> None:
        parts = command_line.split()
        command = parts[0].lower()
        args = parts[1:]

        if command in {"help", "h", "?"}:
            self._show_help()
        elif command == "ls":
            self._list_files()
        elif command == "find":
            self._run_find(args)
        elif command == "generate":
            self._run_generate(args)
        elif command == "inject":
            self._run_inject()
        elif command in {"misc", "miscellaneous"}:
            self._run_misc()
        elif command in {"quit", "exit"}:
            self.exit()
        else:
            self._write("Unknown command. Type `help`.")

    def _show_help(self) -> None:
        self._write("Commands:")
        self._write("  ls")
        self._write("      List selectable files from current directory (.raw/.csv/.txt only).")
        self._write("  find <index> [threshold]")
        self._write("      Run CSV discontinuity analysis on a listed file index.")
        self._write("      Example: find 2 1.0")
        self._write("  generate [nfet|pfet] [model] [width] [length] [output]")
        self._write("      Create a simple SPICE deck (defaults: nfet MDEV 1.0 0.18 generated.sp).")
        self._write("  inject")
        self._write("      Run sample synthetic discontinuity injection.")
        self._write("  misc")
        self._write("      Show extra project details and notes.")
        self._write("  quit")

    def _current_files(self) -> list[Path]:
        return list_supported_files(Path.cwd())

    def _list_files(self) -> None:
        files = self._current_files()
        if not files:
            self._write("No .raw, .csv, or .txt files found in current directory.")
            return
        self._write("Current files:")
        for index, path in enumerate(files, start=1):
            self._write(f"  {index}. {path.name}")

    def _run_find(self, args: list[str]) -> None:
        files = self._current_files()
        if not files:
            self._write("No files available. Use `ls` after adding CSV data.")
            return
        if not args:
            self._write("Usage: find <index> [threshold]")
            self._list_files()
            return
        if not args[0].isdigit():
            self._write("File index must be an integer.")
            return

        selection = int(args[0])
        if not 1 <= selection <= len(files):
            self._write("File index out of range.")
            return

        threshold = 1.0
        if len(args) > 1:
            try:
                threshold = float(args[1])
            except ValueError:
                self._write("Threshold must be numeric.")
                return

        selected_file = files[selection - 1]
        try:
            results = analyze_csv_discontinuities(selected_file, threshold=threshold)
        except Exception as exc:  # surface parser/domain errors in TUI output
            self._write(f"Find failed: {exc}")
            return

        self._write(f"Results for {selected_file.name} (threshold={threshold}):")
        for column, hits in results.items():
            self._write(f"  {column}: {len(hits)} discontinuities")

    def _run_generate(self, args: list[str]) -> None:
        fet_type = "nfet"
        model_name = "MDEV"
        width = 1.0
        length = 0.18
        output = "generated.sp"

        if len(args) > 0:
            fet_type = args[0].lower()
        if len(args) > 1:
            model_name = args[1]
        if len(args) > 2:
            try:
                width = float(args[2])
            except ValueError:
                self._write("Width must be numeric.")
                return
        if len(args) > 3:
            try:
                length = float(args[3])
            except ValueError:
                self._write("Length must be numeric.")
                return
        if len(args) > 4:
            output = args[4]

        if fet_type not in {"nfet", "pfet"}:
            self._write("FET type must be `nfet` or `pfet`.")
            return

        netlist = generate_fet_netlist(
            FetSpec(fet_type=fet_type, model_name=model_name, width=width, length=length),
        )
        Path(output).write_text(netlist, encoding="utf-8")
        self._write(f"Generated {fet_type.upper()} netlist: {output}")

    def _run_inject(self) -> None:
        values = [0.0, 0.2, 0.4, 0.6, 0.8]
        output = inject_random_spikes(values, count=2, magnitude=1.0, seed=42)
        self._write(f"Sample input:  {values}")
        self._write(f"Sample output: {output}")
        self._write("CSV-based injection workflow can be added next.")

    def _run_misc(self) -> None:
        self._write("Miscellaneous:")
        self._write("  - Current find-mode parser target: CSV")
        self._write("  - Add extra utility workflows here as the project grows.")

    def _write(self, message: str) -> None:
        output = self.query_one("#output", Static)
        self._log_lines.append(message)
        output.update("\n".join(self._log_lines[-300:]))


def main() -> None:
    SpiceToolkitApp().run()
