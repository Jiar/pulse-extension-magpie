// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Jiar and contributors
// Synthetic publication artwork, not Pulse UI or a screenshot.
// Uses macOS system fonts, AppKit bitmap drawing, and explicit fictional JSON only.
import AppKit
import Foundation

let arguments = CommandLine.arguments
precondition(arguments.count == 3, "usage: render-demo.swift WORK_FOLDER OUTPUT_FOLDER")
let work = URL(fileURLWithPath: arguments[1], isDirectory: true)
let output = URL(fileURLWithPath: arguments[2], isDirectory: true)
let report = try JSONSerialization.jsonObject(with: Data(contentsOf: work.appendingPathComponent("report.json"))) as! [String: Any]
let limits = report["limits"] as! [[String: Any]]
let providers = try String(contentsOf: work.appendingPathComponent("demo-providers.txt"), encoding: .utf8)
let details = try String(contentsOf: work.appendingPathComponent("demo-details.txt"), encoding: .utf8)

func color(_ hex: String) -> NSColor {
    let value = UInt32(hex.dropFirst(), radix: 16)!
    return NSColor(srgbRed: CGFloat((value >> 16) & 255) / 255,
        green: CGFloat((value >> 8) & 255) / 255,
        blue: CGFloat(value & 255) / 255, alpha: 1)
}
// Role tokens; the single meter series was validated on its dark surface.
let page = color("#f9f9f7")
let ink = color("#151815")
let secondary = color("#52514e")
let surface = color("#1a1a19")
let white = color("#f0efec")
let muted = color("#c3c2b7")
let rule = color("#383835")
let accent = color("#3987e5")
let track = color("#104281")

func fill(_ rect: NSRect, _ tint: NSColor, radius: CGFloat = 0) {
    tint.setFill()
    (radius > 0 ? NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
        : NSBezierPath(rect: rect)).fill()
}

func line(_ x: CGFloat, _ y: CGFloat, _ width: CGFloat, _ tint: NSColor) {
    fill(NSRect(x: x, y: y, width: width, height: 1), tint)
}

@discardableResult
func text(_ string: String, x: CGFloat, y: CGFloat, width: CGFloat,
          size: CGFloat, tint: NSColor = ink, weight: NSFont.Weight = .regular,
          mono: Bool = false, lineHeight: CGFloat? = nil, maxHeight: CGFloat = 200) -> CGFloat {
    let font = mono ? NSFont.monospacedSystemFont(ofSize: size, weight: weight)
        : NSFont.systemFont(ofSize: size, weight: weight)
    let paragraph = NSMutableParagraphStyle()
    paragraph.lineBreakMode = .byWordWrapping
    if let height = lineHeight {
        paragraph.minimumLineHeight = height
        paragraph.maximumLineHeight = height
    }
    let attributes: [NSAttributedString.Key: Any] = [
        .font: font, .foregroundColor: tint, .paragraphStyle: paragraph
    ]
    let attributed = NSAttributedString(string: string, attributes: attributes)
    let bounds = attributed.boundingRect(with: NSSize(width: width, height: 10_000),
        options: [.usesLineFragmentOrigin, .usesFontLeading])
    precondition(bounds.height <= maxHeight + 1,
        "Text would overflow (\(bounds.height) > \(maxHeight)): \(string)")
    attributed.draw(with: NSRect(x: x, y: y, width: width, height: maxHeight),
        options: [.usesLineFragmentOrigin, .usesFontLeading])
    return bounds.height
}

func meter(x: CGFloat, y: CGFloat, width: CGFloat, percent: Double) {
    let height: CGFloat = 8
    fill(NSRect(x: x, y: y, width: width, height: height), track, radius: 4)
    fill(NSRect(x: x, y: y, width: width * CGFloat(percent / 100), height: height), accent, radius: 4)
}

func canvas(width: Int, height: Int, filename: String, drawing: () -> Void) throws {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width,
        pixelsHigh: height, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
        isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: width, height: height)
    let base = NSGraphicsContext(bitmapImageRep: rep)!
    base.cgContext.translateBy(x: 0, y: CGFloat(height))
    base.cgContext.scaleBy(x: 1, y: -1)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(cgContext: base.cgContext, flipped: true)
    fill(NSRect(x: 0, y: 0, width: width, height: height), page)
    drawing()
    NSGraphicsContext.restoreGraphicsState()
    let data = rep.representation(using: .png, properties: [:])!
    try data.write(to: output.appendingPathComponent(filename))
    print("Rendered \(filename) (\(width) × \(height))")
}

func pageHeader(index: String, width: CGFloat) {
    text("PULSE EXTENSION  /  MAGPIE", x: 80, y: 53, width: 800,
        size: 20, weight: .semibold, maxHeight: 28)
    text(index, x: width - 205, y: 53, width: 125, size: 20,
        tint: secondary, mono: true, maxHeight: 28)
    line(80, 100, width - 160, color("#deded7"))
}

func disclaimer(y: CGFloat, width: CGFloat) {
    line(80, y, width - 160, color("#deded7"))
    text("SYNTHETIC ILLUSTRATION · 非实机截图", x: 80, y: y + 20, width: width - 160,
        size: 18, weight: .semibold, maxHeight: 28)
    text("Fictional accounts and values · No live service or private data · Fixed fixture: 2026-11-08 12:00 UTC",
        x: 80, y: y + 52, width: width - 160, size: 17, tint: secondary, maxHeight: 26)
}

func terminal(_ rect: NSRect, title: String) {
    fill(rect, surface, radius: 20)
    text(title, x: rect.minX + 28, y: rect.minY + 22, width: rect.width - 56,
        size: 19, tint: muted, weight: .medium, mono: true, maxHeight: 28)
    line(rect.minX + 28, rect.minY + 65, rect.width - 56, rule)
}

// The overview deliberately illustrates the report rather than reproducing a
// native app window. Every quota label and percentage comes from aggregate_allowances.
try canvas(width: 1600, height: 1280, filename: "magpie-usage.png") {
    pageHeader(index: "01 / 02", width: 1600)
    text("One Magpie account.\nSelected allowances.", x: 80, y: 159, width: 640,
        size: 59, weight: .semibold, lineHeight: 69, maxHeight: 150)
    text("One unified Pulse extension keeps each selected provider’s quota windows together.",
        x: 83, y: 340, width: 560, size: 27, tint: secondary, lineHeight: 37, maxHeight: 120)

    text("A PROVIDER-EQUAL AVERAGE", x: 83, y: 530, width: 570,
        size: 18, weight: .semibold, maxHeight: 30)
    text("Each account contributes its highest quota usage. Accounts are averaged within a provider; providers then receive equal weight.",
        x: 83, y: 575, width: 575, size: 25, tint: secondary, lineHeight: 35, maxHeight: 160)
    fill(NSRect(x: 83, y: 755, width: 570, height: 111), color("#eeeee8"), radius: 12)
    text("Codex: (62 + 34) ÷ 2 = 48%\nUnified: (48 + 52) ÷ 2 = 50%", x: 105, y: 778, width: 526,
        size: 22, weight: .medium, mono: true, lineHeight: 33, maxHeight: 70)

    text("A BALANCE KEEPS ITS OWN UNIT", x: 83, y: 925, width: 570,
        size: 18, weight: .semibold, maxHeight: 30)
    text("The single selected cash balance stays in USD. Hidden Qoder is excluded from this report and its average.",
        x: 83, y: 968, width: 575, size: 25, tint: secondary, lineHeight: 35, maxHeight: 120)

    let card = NSRect(x: 755, y: 159, width: 765, height: 958)
    fill(card, surface, radius: 26)
    text("ILLUSTRATED EXTENSION REPORT", x: 795, y: 194, width: 685,
        size: 16, tint: muted, weight: .medium, maxHeight: 25)
    text("Magpie Usage", x: 795, y: 235, width: 685, size: 33, tint: white,
        weight: .semibold, maxHeight: 45)
    text(report["plan"] as! String, x: 795, y: 287, width: 685,
        size: 20, tint: muted, maxHeight: 29)
    line(795, 335, 685, rule)
    text(limits[0]["label"] as! String, x: 795, y: 363, width: 685,
        size: 24, tint: white, weight: .medium, maxHeight: 36)
    let headline = (limits[0]["usedPercent"] as! NSNumber).doubleValue
    text(String(format: "%.0f%%", headline), x: 795, y: 407, width: 480,
        size: 83, tint: white, weight: .semibold, maxHeight: 105)
    text("used", x: 1026, y: 460, width: 300, size: 23, tint: muted, maxHeight: 34)
    meter(x: 795, y: 526, width: 685, percent: headline)

    for (index, limit) in limits.dropFirst().enumerated() {
        let top = CGFloat(577 + index * 100)
        text(limit["label"] as! String, x: 795, y: top, width: 565,
            size: 22, tint: white, weight: .medium, maxHeight: 31)
        let percentage = (limit["usedPercent"] as! NSNumber).doubleValue
        text(String(format: "%.0f%%", percentage), x: 1390, y: top, width: 90,
            size: 22, tint: white, weight: .medium, mono: true, maxHeight: 31)
        meter(x: 795, y: top + 40, width: 685, percent: percentage)
        let reset = (limit["resetsAt"] as! String).replacingOccurrences(of: "T", with: " ")
            .replacingOccurrences(of: ":00+00:00", with: " UTC")
        text("Resets " + reset, x: 795, y: top + 59, width: 685,
            size: 17, tint: muted, maxHeight: 26)
    }
    line(795, 989, 685, rule)
    let balance = report["balance"] as! [String: Any]
    let amount = (balance["amount"] as! NSNumber).doubleValue
    text("Cursor · orbit-demo · Cash balance", x: 795, y: 1012, width: 685,
        size: 20, tint: muted, maxHeight: 31)
    text(String(format: "%.2f %@", amount, balance["currency"] as! String),
        x: 795, y: 1052, width: 685, size: 27, tint: white, weight: .semibold, maxHeight: 40)
    disclaimer(y: 1160, width: 1600)
}

// Unedited output from the production CLI formatting functions. Draw every
// original line, including blanks; fail instead of clipping any content.
try canvas(width: 1920, height: 1690, filename: "provider-settings.png") {
    pageHeader(index: "02 / 02", width: 1920)
    text("Choose providers. Keep the complete details.", x: 80, y: 146, width: 1760,
        size: 48, weight: .semibold, maxHeight: 68)
    text("Real configure.py output from the synthetic fixture; the CLI text is shown in its original language.",
        x: 82, y: 224, width: 1760, size: 24, tint: secondary, maxHeight: 36)

    let left = NSRect(x: 80, y: 300, width: 570, height: 525)
    terminal(left, title: "configure.print_providers")
    let providerLines = providers.components(separatedBy: "\n")
    for (index, value) in providerLines.enumerated() {
        text(value, x: 108, y: 386 + CGFloat(index * 30), width: 514,
            size: 21, tint: white, mono: true, lineHeight: 30, maxHeight: 31)
    }

    text("SHOW / HIDE BY PROVIDER", x: 83, y: 891, width: 565,
        size: 18, weight: .semibold, maxHeight: 28)
    text("Codex and Cursor are shown. Qoder is hidden. New providers stay hidden by default.",
        x: 83, y: 939, width: 550, size: 26, tint: secondary, lineHeight: 37, maxHeight: 150)
    text("CLI syntax example · not executed", x: 83, y: 1116, width: 550,
        size: 18, tint: secondary, maxHeight: 29)
    fill(NSRect(x: 80, y: 1160, width: 570, height: 166), color("#eeeee8"), radius: 12)
    text("python3 configure.py \\\n  --config /path/to/config.json \\\n  --show codex cursor \\\n  --hide qoder", x: 102, y: 1181, width: 526,
        size: 21, weight: .medium, mono: true, lineHeight: 31, maxHeight: 130)
    text("Complete details also lists hidden sources, original amounts, reset dates, cash and credit balances.",
        x: 83, y: 1382, width: 550, size: 25, tint: secondary, lineHeight: 35, maxHeight: 150)

    let right = NSRect(x: 700, y: 300, width: 1140, height: 1245)
    terminal(right, title: "configure.print_details · complete output")
    let detailLines = details.components(separatedBy: "\n")
    for (index, value) in detailLines.enumerated() {
        let y = 386 + CGFloat(index * 26)
        precondition(y + 27 < right.maxY - 12, "Complete CLI text would be cropped")
        text(value, x: 728, y: y, width: 1084, size: 20, tint: white,
            mono: true, lineHeight: 26, maxHeight: 27)
    }
    disclaimer(y: 1570, width: 1920)
}
