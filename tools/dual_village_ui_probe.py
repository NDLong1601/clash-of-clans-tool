"""Offline Tk visual QA: simulated sessions, temporary config, no ADB/license IO."""

import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import Mock, patch

from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cocmagic import config
from cocmagic.gui import BotPanel, format_run_details


def main():
    output = Path(config.BASE_DIR) / "diagnostics/dual_village_gd7/ui"
    output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    rows = []
    try:
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(config, "SETTINGS_FILE", str(Path(folder) / "settings.json")),
        ):
            client = Mock()
            client.policy.enabled = False
            with (
                patch.object(BotPanel, "_refresh"),
                patch("cocmagic.gui.LicenseClient.from_config", return_value=client),
            ):
                panel = BotPanel(root, initial_port=16384)
            for job in root.tk.call("after", "info"):
                root.after_cancel(job)
            first = panel.tabs["127.0.0.1:16384"]
            second = panel._add_tab(panel.store.add("16416"))
            first.set_online(True)
            second.set_online(True)
            first.run_mode.set("hybrid")
            second.run_mode.set("builder")
            first._save()
            second._save()
            first.session.is_alive = Mock(return_value=True)
            first._set_running(True)
            first.status.set("Recovery · chờ game, chưa xác nhận làng")
            first.run_details.set(
                format_run_details(
                    {
                        "run_mode": "hybrid",
                        "actual_village": "unknown",
                        "builder_bonus_state": "unknown",
                        "builder_incomplete": True,
                        "pending_reason": "recovery",
                        "last_error": "Mất ADB ở bảng xe; chờ ảnh mới, hủy chuỗi input",
                        "next_retry_at": "2026-10-09T15:35:00+07:00",
                        "next_daily_check_at": "2026-10-10T15:30:00+07:00",
                    }
                )
            )
            first._append_log(
                "[QA] Dữ liệu phiên giả lập để kiểm tra giao diện offline.\n" * 3
            )
            panel._update_summary()
            for size in ("980x840", "880x680"):
                root.geometry(size + "+30+30")
                for key, index in (("main", 0), ("builder", 1), ("run", 2)):
                    panel.notebook.select(first.frame)
                    first.notebook.select(index)
                    first.canvases[key].yview_moveto(0)
                    root.update()
                    root.update_idletasks()
                    path = output / f"{size}-{key}.png"
                    ImageGrab.grab(window=root.winfo_id()).save(path)
                    rows.append(
                        {
                            "size": size,
                            "page": key,
                            "image": path.name,
                            "canvas_width": first.canvases[key].winfo_width(),
                            "content_width": first.pages[key].winfo_width(),
                            "locked": all(
                                str(w.cget("state")) == "disabled" for w in first.inputs
                            ),
                        }
                    )
                first.canvases["run"].yview_moveto(1)
                root.update()
                ImageGrab.grab(window=root.winfo_id()).save(
                    output / f"{size}-run-bottom.png"
                )
            panel.notebook.select(second.frame)
            second.notebook.select(1)
            root.update()
            ImageGrab.grab(window=root.winfo_id()).save(
                output / "880x680-second-builder.png"
            )
            (output / "receipt.json").write_text(
                json.dumps(
                    {
                        "evidence": "offline Tk, simulated sessions; no gameplay",
                        "capture": "Pillow window handle; independent of desktop foreground",
                        "rows": rows,
                        "second_editable": str(
                            second.mode_buttons["builder"].cget("state")
                        ),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
    finally:
        root.destroy()
    print(output)


if __name__ == "__main__":
    main()
