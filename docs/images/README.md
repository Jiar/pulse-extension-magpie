# Product images

The main README uses a five-provider product illustration with wholly fictional data. Two additional synthetic illustrations explain the extension's report and provider switches.

## Product overview

[magpie-product-overview.png](magpie-product-overview.png) is a **1800 × 1440** product illustration, not a native Pulse screenshot. A neutral background, generous margins, and soft shadows frame a compact quota card and its outer average-usage ring. It contains exactly five service rows, plus their average in the summary.

All account names, quota readings, and reset dates are fictional. The following table is the text equivalent of the five rows; the fixed fixture clock is **2026-11-08 12:00 UTC**.

| Service | Fictional account | Quota window | Used | Resets at (UTC) |
| --- | --- | --- | --- | --- |
| Codex | cedar-demo | 7 days | 18% | 2026-11-15 12:00 |
| Cursor | orbit-demo | Monthly | 32% | 2026-12-01 00:00 |
| OpenCode Go | lumen-demo | 5 hours | 44% | 2026-11-08 15:00 |
| Qoder | fern-demo | Monthly | 37% | 2026-12-01 00:00 |
| WorkBuddy | birch-demo | Monthly | 49% | 2026-11-30 00:00 |

Each service has one account with one quota window, so the equal-provider average is **(18 + 32 + 44 + 37 + 49) / 5 = 36%**. The production `magpie.aggregate_allowances` function computed this value from the synthetic rows, with live fetch and config reads disabled. The summary and outer ring both use that same computed result.

The artwork was drawn offline with Pillow and macOS system fonts. No installed application was launched, desktop captured, live service contacted, or real account configuration read. The flattened RGB PNG contains only image chunks, with no text, EXIF, source paths, embedded original, or thumbnail metadata. No font binaries are distributed. The `render-demo.py` command below generates only the two additional illustrations, not this product overview.

The depicted card layout requires the native Pulse scrolling changes. The extension now installs a Magpie icon, but displaying it also requires Pulse's optional manifest `icon` support. Installing the Python extension alone does not update Pulse. This illustration does not establish exact native rendering or interaction behavior. See [Pulse capability boundaries](../../README.md#pulse-能力边界) and [the optional native changes](../../native-pulse/README.md).

The Magpie logo identifies the displayed integration. The repository also provides [magpie-icon.png](../../magpie-icon.png), a 256 × 256 PNG installed alongside the extension and declared by its manifest's optional `icon` field. It was resized and re-encoded from the Magpie application icon without retaining metadata. Pulse must support that field to draw it. Rights to the third-party artwork and mark remain with their owners; the repository's Apache-2.0 license grants no rights to that artwork or any trademark. See [NOTICE](../../NOTICE).

## Additional synthetic illustrations

The following two images are **synthetic illustrations (非实机截图)**, not screenshots of Pulse, Magpie, or native SwiftUI components. The artwork is drawn directly into AppKit bitmaps. No application or window is opened and no screen is captured by their renderer.

| Image | Content | Size |
| --- | --- | --- |
| [magpie-usage.png](magpie-usage.png) | Illustrated unified report: provider-equal average, all selected quota windows, reset dates, and one cash balance | 1600 × 1280 |
| [provider-settings.png](provider-settings.png) | The complete, unedited output of `configure.print_providers` and `configure.print_details`, plus an explicitly unexecuted CLI syntax example | 1920 × 1690 |

Suggested captions:

- **Magpie Usage 合成示意（非实机截图）。** 虚构数据展示统一扩展的服务商等权平均、各账号额度窗口、重置时间与独立余额。
- **服务商显示/隐藏与完整额度（合成示意，非实机截图）。** `configure.py` 的原样文本输出由虚构 fixture 生成；完整额度仍列出隐藏来源。

### Reproduce

From the extension repository root, on macOS with Python 3 and full Xcode installed:

```bash
python3 -I scripts/render-demo.py
```

The script uses only Python's standard library, `xcrun swift`, Foundation, AppKit, macOS system fonts, and simple drawing geometry. It needs no native Pulse checkout, third-party Python packages, network access, installed application, account, credential, or user configuration. It does not invoke the `magpie.py` or `configure.py` command-line entry points.

The renderer reads [the synthetic fixture](../demo-allowances.json), imports the local core modules, and calls only the pure conversion/formatting functions: `aggregate_allowances`, `print_providers`, and `print_details`. It replaces the modules' live fetch and config-read functions with guards that raise an error if called. The fixture clock is fixed at **2026-11-08 12:00 UTC**. Temporary inputs live in a fresh `.local/demo-*` directory; public outputs are written only into `docs/images/`. The native source fork and installed applications are not read or changed by this generation command.

For text and data only, without compiling the AppKit renderer:

```bash
python3 -I scripts/render-demo.py --data-only
```

The generated accessible equivalents are [demo-report.json](demo-report.json), [demo-providers.txt](demo-providers.txt), and [demo-details.txt](demo-details.txt). [render-manifest.json](render-manifest.json) records the fixture, core source, report, and PNG SHA-256 hashes. The same inputs reproduce the same values and layout; AppKit text rasterization may vary across macOS, Xcode, and system font versions. Repeated generation was checked for byte-identical PNGs on the generation machine. The renderer strips ancillary metadata, including AppKit's automatic EXIF chunk; the delivered PNGs contain only image data and the sRGB color declaration.

### Accuracy and privacy

All names, dates, usage amounts, balances, plans, and settings are invented. The stable account names are `cedar-demo`, `lumen-demo`, `orbit-demo`, and `fern-demo`. There are no email addresses, redacted originals, account identifiers copied from a real account, or real service responses.

The selected Codex account peaks are 62% and 34%, so Codex contributes 48%. Cursor contributes 52%. Their equal-weight average is 50%. Hidden Qoder does not appear in the unified report or average, but remains in the complete CLI output. The 18.40 USD cash balance remains separate from quota percentages and the hidden Qoder credit balance. The four selected quota windows and their reset dates are shown in the overview. The overview is selective about ancillary metrics; the raw report and complete details retain the additional source-age/reset information.

The illustrated layout, typography, and bars are publication artwork, not a claim about exact Pulse UI layout, a native rendering, a settings window, actual interaction, or screen behavior. The CLI example is syntax only and was not executed. The original Chinese CLI text is preserved rather than translated or rewritten. This offline renderer does not compile or use Pulse's native components.

### Artwork and attribution

These two synthetic illustrations redistribute no Magpie icon, provider logo, native screenshot, upstream artwork, external image, third-party font file, or font binary. They use macOS system text rendering and original simple geometry. The single usage-meter color is `#3987e5` on `#1a1a19`. Every meter has a direct numeric label, and text/data equivalents accompany the images.

These synthetic illustrations and their renderer scripts are covered by the repository's [Apache-2.0 license](../../LICENSE). They add no third-party artwork attribution requirement. Upstream code attribution is preserved in [NOTICE](../../NOTICE).
