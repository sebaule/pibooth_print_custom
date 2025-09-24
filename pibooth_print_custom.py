# pibooth_print_custom.py
# ---------------------------------------------------------------------
# Custom ESC/POS printer plugin for Pibooth
# - Builds a command line to call /home/seb/print_raster.py
# - Configurable through [ESC_POS] section in pibooth.cfg
# - Boolean flags + numeric/path options with "empty = disabled" behavior
# - Includes "limit_lines" and "pre_cancel" (flush/reset before printing)
# - Concise logging for troubleshooting (command + outputs)
# ---------------------------------------------------------------------

import os
import shlex
import subprocess
import logging
import pibooth
from pibooth.printer import Printer

LOGGER = logging.getLogger("pibooth")
__version__ = "3.2.0"
SECTION = "ESC_POS"


@pibooth.hookimpl
def pibooth_configure(cfg):
    """
    Register [ESC_POS] options in Pibooth configuration.

    NOTE about numeric/path options:
      - They are stored as strings to allow "empty = disabled".
      - If a value is left empty in pibooth.cfg, the plugin will NOT send the flag.
    """
    # Core paths and dimensions
    cfg.add_option(SECTION, "script_path", "/home/seb/print_raster.py",
                   "Path to the ESC/POS printing script (default: /home/seb/print_raster.py)")
    cfg.add_option(SECTION, "serial_device", "/dev/ttyS0",
                   "Thermal printer serial device (default: /dev/ttyS0)")
    cfg.add_option(SECTION, "target_width", 384,
                   "Target image width in pixels (default: 384)")

    # Serial speed (string to allow empty => disabled => script default 9600)
    cfg.add_option(SECTION, "baudrate", "9600",
                   "Serial speed in baud (default: 9600). Recommended: 9600 (stable), 19200, 38400. "
                   "Leave empty to use the script default.")

    # Booleans
    cfg.add_option(SECTION, "no_autorotate", False,
                   "Disable automatic portrait rotation (adds --no-autorotate) (default: False)")
    cfg.add_option(SECTION, "pre_cancel", True,
                   "Flush/cancel/reset before printing (adds --pre-cancel) (default: True)")
    cfg.add_option(SECTION, "invert", True,
                   "Invert black/white (adds --invert) (default: True)")
    cfg.add_option(SECTION, "no_dither", False,
                   "Disable dithering (adds --no-dither) (default: False). "
                   "If False => threshold is ignored by the script.")

    # Numeric/float options as strings (empty => not sent)
    cfg.add_option(SECTION, "threshold", "130",
                   "Threshold if --no-dither is True (0..255). Empty = disabled. (default: 130)")
    cfg.add_option(SECTION, "contrast", "1.3",
                   "Contrast before binarization. Empty = disabled. (default: 1.3)")
    cfg.add_option(SECTION, "gamma", "",
                   "Gamma correction. Empty = disabled. (default: disabled)")
    cfg.add_option(SECTION, "chunk", "4096",
                   "Serial write chunk size in bytes. Empty = disabled. (default: 4096)")
    cfg.add_option(SECTION, "line_sleep", "0.02",
                   "Pause between raster bands in seconds. Empty = disabled. (default: 0.02)")
    cfg.add_option(SECTION, "limit_lines", "",
                   "Limit number of printed lines (debug/paper save). Empty = disabled. (default: disabled)")

    # Debug outputs (empty => not sent)
    cfg.add_option(SECTION, "preview", "",
                   "Path to save the 1-bit preview image. Empty = disabled. (default: disabled)")
    cfg.add_option(SECTION, "dry_run", "",
                   "Path to save ESC/POS stream to file (no print). Empty = disabled. (default: disabled)")


class CustomPrinter(Printer):
    """
    Custom Pibooth printer that shells out to print_raster.py using configured flags.
    """
    def __init__(self, name, max_pages, options, cfg):
        super().__init__(name, max_pages, options)
        self.cfg = cfg

    # ---------- Small helpers to safely add flags ----------

    def _add_bool_flag(self, cmd, flag, enabled):
        """Append a boolean flag if enabled."""
        if enabled:
            cmd.append(flag)

    def _add_numeric_option(self, cmd, flag, value_str, cast):
        """
        Append a numeric flag with value if value_str is not empty.
        - value_str: raw string from cfg (may be empty => skip)
        - cast: callable to validate type (int/float)
        """
        vs = (value_str or "").strip()
        if vs == "":
            return
        try:
            _ = cast(vs)  # validate type
            cmd.extend([flag, vs])
        except Exception:
            LOGGER.warning("[ESC_POS] Invalid value for %s: '%s' (skipped)", flag, value_str)

    def _add_path_option(self, cmd, flag, path_value):
        """Append a CLI path option if provided (non-empty)."""
        pv = (path_value or "").strip()
        if pv:
            cmd.extend([flag, pv])

    # ---------- Command builder ----------

    def build_command(self, filename):
        """Build the full subprocess command to call print_raster.py."""
        script_path = self.cfg.get(SECTION, "script_path")
        serial_device = self.cfg.get(SECTION, "serial_device")
        target_width = str(self.cfg.getint(SECTION, "target_width"))

        cmd = [
            "python3", script_path,
            "--print", filename,
            "--dev", serial_device,
            "--width", target_width,
        ]

        # Serial speed (empty => use script default)
        self._add_numeric_option(cmd, "--baud", self.cfg.get(SECTION, "baudrate"), int)

        # Boolean flags
        self._add_bool_flag(cmd, "--no-autorotate", self.cfg.getboolean(SECTION, "no_autorotate"))
        self._add_bool_flag(cmd, "--pre-cancel", self.cfg.getboolean(SECTION, "pre_cancel"))
        self._add_bool_flag(cmd, "--invert", self.cfg.getboolean(SECTION, "invert"))

        no_dither = self.cfg.getboolean(SECTION, "no_dither")
        self._add_bool_flag(cmd, "--no-dither", no_dither)

        # Numeric/float options (empty => disabled)
        # NOTE: threshold is only used by the script when --no-dither is enabled
        thr_value = (self.cfg.get(SECTION, "threshold") or "").strip()
        if no_dither:
            self._add_numeric_option(cmd, "--threshold", thr_value, int)
        # If no_dither is False and threshold is set, script ignores it—no need to warn every time

        self._add_numeric_option(cmd, "--contrast", self.cfg.get(SECTION, "contrast"), float)
        self._add_numeric_option(cmd, "--gamma", self.cfg.get(SECTION, "gamma"), float)
        self._add_numeric_option(cmd, "--chunk", self.cfg.get(SECTION, "chunk"), int)
        self._add_numeric_option(cmd, "--line-sleep", self.cfg.get(SECTION, "line_sleep"), float)
        self._add_numeric_option(cmd, "--limit-lines", self.cfg.get(SECTION, "limit_lines"), int)

        # Debug outputs (empty => disabled)
        self._add_path_option(cmd, "--preview", self.cfg.get(SECTION, "preview"))
        self._add_path_option(cmd, "--dry-run", self.cfg.get(SECTION, "dry_run"))

        return cmd

    # ---------- Printing entry point ----------

    def print_file(self, filename, copies=1):
        """
        Main printing logic called by Pibooth.
        - Builds the command line from configuration
        - Runs the script as a subprocess
        - Logs stdout/stderr for troubleshooting
        """
        if not filename or not os.path.exists(filename):
            LOGGER.warning("[ESC_POS] No photo to print (missing file).")
            return

        script_path = self.cfg.get(SECTION, "script_path")
        if not os.path.exists(script_path):
            LOGGER.error("[ESC_POS] Print script not found: %s", script_path)
            return

        serial_device = self.cfg.get(SECTION, "serial_device")
        target_width = self.cfg.getint(SECTION, "target_width")
        LOGGER.info("[ESC_POS] Printing via ESC/POS")
        LOGGER.info("[ESC_POS] Image: %s", filename)
        LOGGER.info("[ESC_POS] Script: %s | Serial: %s | Width: %d px", script_path, serial_device, target_width)

        for i in range(copies):
            LOGGER.info("[ESC_POS] Start copy %d/%d", i + 1, copies)
            cmd = self.build_command(filename)
            cmd_str = " ".join(shlex.quote(p) for p in cmd)
            LOGGER.debug("[ESC_POS] Command: %s", cmd_str)

            try:
                res = subprocess.run(cmd, check=True, capture_output=True, text=True)
                if res.stdout:
                    LOGGER.debug("[ESC_POS] print_raster.py stdout:\n%s", res.stdout.strip())
                if res.stderr:
                    # The script logs to stderr by design; treat it as info, not as an error
                    LOGGER.info("[ESC_POS] print_raster.py stderr:\n%s", res.stderr.strip())
                LOGGER.info("[ESC_POS] Copy %d/%d finished.", i + 1, copies)
            except subprocess.CalledProcessError as e:
                LOGGER.error(
                    "[ESC_POS] Printing failure (exit code %s)\n"
                    "Command: %s\n"
                    "STDOUT :\n%s\n"
                    "STDERR :\n%s",
                    e.returncode, cmd_str, (e.stdout or "").strip(), (e.stderr or "").strip()
                )
                # Re-raise so Pibooth can react (counters, UI, etc.)
                raise


@pibooth.hookimpl
def pibooth_setup_printer(cfg):
    LOGGER.info(">>> Hook pibooth_setup_printer (ESC/POS)")
    return CustomPrinter(cfg.get("PRINTER", "printer_name"),
                         cfg.getint("PRINTER", "max_pages"),
                         cfg.gettyped("PRINTER", "printer_options"),
                         cfg)
