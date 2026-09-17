# `ocrdeskew --json` schema (verified)

Captured from `ocrdeskew` app_version `2.0.1`, schema_version `ocrdeskew.cli.v1`. Re-verify after an app update.

## Top level

```json
{
  "app_version": "2.0.1",
  "lang": "eng",
  "quality": "fast",
  "results": "<list of result entries>",
  "schema_version": "ocrdeskew.cli.v1"
}
```

## `results[]` entry

| Key | Type | Notes |
|---|---|---|
| `ok` | bool | Success flag. **Not** `success`. |
| `error` | str/null | Failure reason when `ok` is false. |
| `input_path` | str | Source path. **Not** `input`. |
| `output_path` | str | PDF written. |
| `result` | object | OCR metadata, below. |

## `result` keys

| Key | Example |
|---|---|
| `angle` | `0.0` |
| `angles_tested` | _list, omitted here_ |
| `audit_status` | `"Needs OCR"` |
| `confidence` | `87.4022641509434` |
| `dpi_used` | `300` |
| `engine_used` | `"tesseract"` |
| `escalation_tier` | `0` |
| `estimated_angle` | `-2.220446049250313e-16` |
| `orientation_applied` | `0` |
| `pages_processed` | `1` |
| `per_page` | _list, omitted here_ |
| `quality_score` | `87.4022641509434` |
| `repair_action` | `"Deskew + OCR"` |
| `text` | _str, omitted here_ |
| `variants_tried` | `1` |
| `word_count` | `106` |

## `result.per_page[]` keys

```
attempts, chosen_recipe, confidence, deskew_angle, diagnosis, dpi_used, elapsed_ms, engine_used, orientation_applied, output_dpi, output_height_points, output_height_px, output_width_points, output_width_px, page_index, psm, quality_score, text, tier, word_boxes, word_count
```

`diagnosis` holds: `bleed_through`, `blur_metric`, `contrast`, `effective_dpi`, `ink_coverage`, `large_component_count`, `noise_level`, `orientation`, `skew_angle`.

`word_boxes` holds one `{text, confidence, left, top, width, height}` object per word.

## Notes

- With `--out DIR` the output keeps the source stem (`scan.pdf`). With no
  `--out`, `ocrdeskew` writes a `-deskewed` sidecar next to the source.
- `shotgun.py` always names its output `<stem>-deskewed.pdf`, so it can never
  silently overwrite a source when the output directory is the source directory.
