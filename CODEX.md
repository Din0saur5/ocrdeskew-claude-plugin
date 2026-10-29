# OCRDeskew for Codex and ChatGPT desktop

This repository now packages the same local OCRDeskew helpers for both Claude
Code and Codex. The existing Claude install commands remain unchanged.

The portable root `plugin.json` exposes five Codex skills: `ocrdeskew`,
`ocr-audit`, `ocr-batch`, `ocr-unlock`, and `ocr-triage`. Both integrations use
the Python helpers in `claude-plugin/skills/ocrdeskew/scripts/`; there is no
second OCR implementation or duplicated helper tree.

## Install

Use a current ChatGPT desktop/Codex client with local plugin support. The repo
marketplace is `.agents/plugins/marketplace.json`. From a supported Codex CLI:

```bash
codex plugin marketplace add Din0saur5/ocrdeskew-claude-plugin --ref main
```

Open the Plugins Directory in the desktop app, choose **OCRDeskew Plugins**,
and install **OCRDeskew**. Restart/refresh the client if needed. The old standalone
Codex CLI may not support `plugin marketplace`; update to a client with local
plugin support before using this command. This repository entry makes the
plugin available; it does not automatically enable it or publish a public listing.

The public repository marketplace is available to anyone with a supported local
client. It is separate from OpenAI’s reviewed public Plugins Directory.

Alternatively, download `ocrdeskew-codex-plugin.zip` from the repository’s
[latest Codex release](https://github.com/Din0saur5/ocrdeskew-claude-plugin/releases/latest).
For local development, add the checkout path instead of the GitHub repository.

Try these in Codex (or select the corresponding skill in the desktop app):

```text
$ocr-audit Assess ./production without changing originals.
$ocr-batch Repair ./production using balanced quality, working copies in ./repaired, and parallel processing.
$ocr-unlock Write unlocked copies of the PDFs in ./production.
$ocr-triage Review ./ocr-report.json and recommend next steps.
```

These are skills, not Claude's `/ocr-*` slash commands. The triage workflow is
a skill rather than a Claude-specific subagent. Capability and shared helpers
are the same; host invocation differs.

## Requirements and processing

- Local command execution and access to the input files. This is not a
  browser-only ChatGPT integration.
- OCRDeskew installed, its `ocrdeskew` CLI on PATH, and an active trial/license
  for OCR. The plugin is free; OCRDeskew is licensed separately.
- Python 3 for helpers; qpdf or pypdf for PDF batching; pypdf or PyPDF2 for unlock.
- macOS or Windows with these dependencies installed. Windows Python commands
  may be `python` or `py -3` instead of `python3`.

OCR and the helpers execute locally. The assistant still uses its configured
AI service. The skills keep file bytes and extracted document text in local
reports and summarize metadata. External image analysis is a separate decision.

## Package and verify

```bash
python3 scripts/package_codex_plugin.py --out /tmp/ocrdeskew-codex-plugin.zip
python3 -m pip install pypdf
python3 -m unittest discover -s tests -v
```

The ZIP contains the root manifest, Codex skills, shared helper scripts and
references, license, and documentation. It excludes Git history, caches, and
user files. Import/distribution still depends on the target client's supported
plugin flow; this is not a claim of public marketplace approval.

Official format and local-install instructions:
https://developers.openai.com/plugins/build/plugins
https://developers.openai.com/plugins/deploy/desktop-only
