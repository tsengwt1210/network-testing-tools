"""Offline checks of the implemented bit mapping, not modem NV definitions."""

import csv
import importlib.util
import io
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "nv" / "nv_band_preference_tool.py"
SPEC = importlib.util.spec_from_file_location("nv_under_test", SOURCE)
nv = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = nv
SPEC.loader.exec_module(nv)


class BitMappingTests(unittest.TestCase):
    def test_field_boundaries_and_n277(self):
        expected = {
            1: [1, 0, 0, 0, 0],
            64: [1 << 63, 0, 0, 0, 0],
            65: [0, 1, 0, 0, 0],
            128: [0, 1 << 63, 0, 0, 0],
            277: [0, 0, 0, 0, 1 << 20],
            320: [0, 0, 0, 0, 1 << 63],
        }
        for band, fields in expected.items():
            with self.subTest(band=band):
                self.assertEqual(nv.encode_bands([band], 5), fields)
                self.assertEqual(nv.decode_values(fields), [band])

    def test_known_example(self):
        self.assertEqual(nv.encode_bands([1, 8, 20], 1), [524417])
        self.assertEqual(nv.format_hex(524417), "0x0000000000080081")
        self.assertEqual(nv.mapping_detail([277]), [(277, "bits_257_320", 21, 20, 1048576)])

    def test_every_single_bit_roundtrip(self):
        for band in range(1, 321):
            with self.subTest(band=band):
                self.assertEqual(nv.decode_values(nv.encode_bands([band], 5)), [band])

    def test_random_combination_roundtrip(self):
        rng = random.Random(42)
        for field_count in (1, 5):
            for _ in range(50):
                bands = sorted(rng.sample(range(1, field_count * 64 + 1), rng.randrange(field_count * 64 + 1)))
                self.assertEqual(nv.decode_values(nv.encode_bands(bands, field_count)), bands)

    def test_empty_and_duplicate_inputs(self):
        self.assertEqual(nv.encode_bands([], 5), [0] * 5)
        self.assertEqual(nv.decode_values([0] * 5), [])
        self.assertEqual(nv.encode_bands([8, 1, 8, 20], 1), [524417])

    def test_out_of_range_and_noninteger_bands_rejected(self):
        for band in (0, -1, 321, 512, 1.5, "1", True):
            with self.subTest(band=band), self.assertRaises(ValueError):
                nv.encode_bands([band], 5)
        with self.assertRaises(ValueError):
            nv.encode_bands([65], 1)
        for field_count in (0, -1, 1.5, True):
            with self.subTest(field_count=field_count), self.assertRaises(ValueError):
                nv.encode_bands([1], field_count)

    def test_invalid_uint64_fields_rejected(self):
        for value in (-1, 1 << 64, 1.5, "1", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                nv.decode_values([value])
        self.assertEqual(nv.decode_values([nv.MAX_UINT64]), list(range(1, 65)))


class InputTests(unittest.TestCase):
    def test_band_input_formats(self):
        for text in ("B1, n8; 20", "Band 1 LTE 8 NR 20", "1，8；20"):
            with self.subTest(text=text):
                self.assertEqual(nv.parse_bands(text, 64), [1, 8, 20])
        self.assertEqual(nv.parse_bands("3-1, 8~9, 20–21", 64), [1, 2, 3, 8, 9, 20, 21])
        self.assertEqual(nv.parse_bands("", 320), [])

    def test_invalid_band_input(self):
        for text in ("0", "-1", "321", "512", "1-321", "0-2", "a", "1-2-3"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                nv.parse_bands(text, 320)

    def test_large_invalid_range_is_rejected_before_expansion(self):
        with patch.object(nv, "range", create=True, side_effect=AssertionError("range was expanded")):
            with self.assertRaises(ValueError):
                nv.parse_bands("1-999999999999999999", 320)

    def test_uint64_input_formats_and_limits(self):
        for text in ("524417", "524,417", "524_417", "0x0000000000080081", "0524417"):
            with self.subTest(text=text):
                self.assertEqual(nv.parse_integer(text), 524417)
        self.assertEqual(nv.parse_integer(""), 0)
        self.assertEqual(nv.parse_integer(str(nv.MAX_UINT64)), nv.MAX_UINT64)
        for text in ("-1", str(1 << 64), "0x10000000000000000", "garbage"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                nv.parse_integer(text)

    def test_profile_limits_are_not_radio_compatibility_claims(self):
        for nv_id in (74087, 74213):
            self.assertEqual(nv.B45_NV_ITEMS[nv_id].field_count, 5)
            self.assertEqual(nv.B45_NV_ITEMS[nv_id].max_band, 320)
        self.assertEqual(nv.B45_OverviewPage.QUICK_NR_MAX_BAND, 128)


class ValueStub:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class MemoryFile(io.StringIO):
    def close(self):
        # Keep content available after the production code's with statement.
        pass


class CsvExportTests(unittest.TestCase):
    def page(self, definition, bands, values):
        return SimpleNamespace(
            definition=definition,
            band_var=ValueStub(bands),
            value_vars=[ValueStub(str(value)) for value in values],
            status_callback=lambda _message: None,
        )

    def test_conflicting_inputs_are_blocked_before_save_dialog(self):
        for cls, definition in (
            (nv.B45_NVPage, nv.B45_NV_ITEMS[65633]),
            (nv.B34_NVPage, nv.B34_NV_ITEMS[6828]),
        ):
            for bands, values in (("8", [1]), ("1", [128])):
                with self.subTest(page=cls.__name__, bands=bands):
                    page = self.page(definition, bands, values)
                    with patch.object(nv.messagebox, "showerror") as error, patch.object(nv.filedialog, "asksaveasfilename") as save:
                        cls.export_csv(page)
                    error.assert_called_once()
                    self.assertIn("do not match", error.call_args.args[1])
                    save.assert_not_called()

    def test_exported_values_and_band_lists_are_consistent(self):
        for cls, definition, bands in (
            (nv.B45_NVPage, nv.B45_NV_ITEMS[74087], [1, 64, 65, 128, 277, 320]),
            (nv.B34_NVPage, nv.B34_NV_ITEMS[6828], [1, 8, 20]),
        ):
            with self.subTest(page=cls.__name__):
                values = nv.encode_bands(bands, definition.field_count)
                page = self.page(definition, ",".join(map(str, bands)), values)
                output = MemoryFile()
                with patch.object(nv.filedialog, "asksaveasfilename", return_value="unused.csv"), patch("builtins.open", return_value=output):
                    cls.export_csv(page)
                rows = list(csv.reader(io.StringIO(output.getvalue())))
                header = rows.index(["INPUT Field", "Band Range", "Decimal", "HEX", "Enabled Bands"])
                for index, row in enumerate(rows[header + 1:header + 1 + definition.field_count]):
                    expected_bands = [band for band in bands if (band - 1) // 64 == index]
                    self.assertEqual(int(row[2]), values[index])
                    self.assertEqual(row[3], nv.format_hex(values[index]))
                    self.assertEqual(row[4], ", ".join(map(str, expected_bands)))


if __name__ == "__main__":
    unittest.main()
