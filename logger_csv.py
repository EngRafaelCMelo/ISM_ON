import csv
import os
from datetime import datetime

class CsvLogger:
    def __init__(self, folder: str, file_prefix: str, channel_names: list[str]):
        os.makedirs(folder, exist_ok=True)
        self.channel_names = list(channel_names)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(folder, f"{file_prefix}_{ts}.csv")

        self.file = open(self.path, "w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)

        header = ["timestamp_iso"]
        for name in channel_names:
            header.extend([f"{name}_mA", f"{name}_raw", f"{name}_calibrated", f"{name}_status"])
        self.writer.writerow(header)
        self.file.flush()

    def write_row(
        self,
        timestamp_iso: str,
        currents_mA: list[float],
        eng_values: list[float],
        statuses: list[str] | None = None,
        eng_raw: list[float] | None = None,
    ):
        statuses = statuses or [""] * len(self.channel_names)
        eng_raw = eng_raw or [None] * len(self.channel_names)
        row = [timestamp_iso]
        for i, _ in enumerate(self.channel_names):
            row.extend([
                currents_mA[i] if i < len(currents_mA) else None,
                eng_raw[i] if i < len(eng_raw) else None,
                eng_values[i] if i < len(eng_values) else None,
                statuses[i] if i < len(statuses) else "",
            ])
        self.writer.writerow(row)
        self.file.flush()

    def close(self):
        try:
            self.file.close()
        except Exception:
            pass
