import csv

from logger_csv import CsvLogger


def test_csv_preserves_missing_values_and_separates_raw_calibrated(tmp_path):
    logger = CsvLogger(str(tmp_path), "test", ["P1", "DP"])
    logger.write_row("2026-01-01T00:00:00+00:00", [4.0, 3.0], [0.0, None], ["OK", "OPEN_LOOP"], [0.0, -12.5])
    logger.close()
    rows = list(csv.reader(open(logger.path, encoding="utf-8", newline="")))
    assert "P1_raw" in rows[0]
    assert "P1_calibrated" in rows[0]
    assert rows[1][rows[0].index("DP_calibrated")] == ""
