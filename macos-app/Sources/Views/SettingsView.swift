import AppKit
import SwiftUI

/// 原生设置窗口：通用 / 外观 / 关于。
/// 所有控件都接真实状态：输出目录走 backend API，主题写入 UserDefaults 并即时预览。
public struct SettingsView: View {
    @ObservedObject private var settings = AppSettings.shared
    @ObservedObject private var manager = BackendManager.shared
    @State private var selectedTab: SettingsTab = .general

    public init() {}

    public var body: some View {
        TabView(selection: $selectedTab) {
            generalTab
                .tabItem { Label("通用", systemImage: "slider.horizontal.3") }
                .tag(SettingsTab.general)

            appearanceTab
                .tabItem { Label("外观", systemImage: "paintpalette") }
                .tag(SettingsTab.appearance)

            aboutTab
                .tabItem { Label("关于", systemImage: "info.circle") }
                .tag(SettingsTab.about)
        }
        .frame(width: 640, height: 560)
        .background(LightTheme.canvas)
    }

    // MARK: - General

    private var generalTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                pageTitle("通用", subtitle: "输出位置与默认转换策略")

                card {
                    VStack(alignment: .leading, spacing: 14) {
                        cardHeader(
                            "输出文件夹",
                            subtitle: "Studio 新任务会把交付物写入这里；原始 PDF 仍归档到项目的 processed/。"
                        )

                        HStack(alignment: .top, spacing: 11) {
                            Image(systemName: "folder.fill")
                                .font(.system(size: 15, weight: .medium))
                                .foregroundStyle(LightTheme.accentBlue)
                                .frame(width: 30, height: 30)
                                .background(
                                    LightTheme.accentBlue.opacity(0.10),
                                    in: RoundedRectangle(cornerRadius: 8, style: .continuous)
                                )

                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 6) {
                                    Text(manager.isUsingCustomOutputFolder ? "自定义文件夹" : "默认成果目录")
                                        .font(.system(size: 12.5, weight: .semibold))
                                        .foregroundStyle(LightTheme.textPrimary)

                                    if manager.isSyncingOutputFolder {
                                        ProgressView()
                                            .controlSize(.mini)
                                    }
                                }

                                Text(manager.outputFolderDisplayPath)
                                    .font(.system(size: 11.5, design: .monospaced))
                                    .foregroundStyle(LightTheme.textSecondary)
                                    .lineLimit(2)
                                    .textSelection(.enabled)
                            }

                            Spacer(minLength: 8)
                        }

                        HStack(spacing: 8) {
                            Button("选择…") {
                                chooseOutputFolder()
                            }
                            .buttonStyle(PressableButtonStyle())
                            .lightButton(isProminent: true)

                            Button("在访达中显示") {
                                manager.revealOutbox()
                            }
                            .buttonStyle(PressableButtonStyle())
                            .lightButton()

                            Button("恢复默认") {
                                settings.resetOutputFolder()
                                manager.syncOutputFolderIfNeeded(force: true)
                            }
                            .buttonStyle(PressableButtonStyle())
                            .lightButton()
                            .disabled(!manager.isUsingCustomOutputFolder)
                        }

                        if let error = manager.outputFolderError {
                            Label(error, systemImage: "exclamationmark.triangle.fill")
                                .font(.system(size: 11.5))
                                .foregroundStyle(LightTheme.accentRed)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }

                card {
                    VStack(alignment: .leading, spacing: 14) {
                        cardHeader(
                            "默认转换策略",
                            subtitle: "默认采用智能双轨自动判别文献类型；原始 PDF 不离机。"
                        )

                        settingRow(
                            title: "翻译服务",
                            detail: manager.selectedService == .google
                                ? "Google 用于矢量正文；扫描件及表格、图中文字使用本地翻译。"
                                : "在线翻译会发送提取的文字，原始 PDF 不上传。"
                        ) {
                            Picker("翻译服务", selection: $manager.selectedService) {
                                ForEach(TranslationService.allCases) { service in
                                    Text(service.shortTitle)
                                        .tag(service)
                                }
                            }
                            .labelsHidden()
                            .pickerStyle(.menu)
                            .frame(width: 220, alignment: .trailing)
                        }
                    }
                }

                card {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("任务记录")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(LightTheme.textPrimary)

                            Text("已完成任务只保留在本次运行的内存列表中。")
                                .font(.system(size: 11.5))
                                .foregroundStyle(LightTheme.textSecondary)
                        }

                        Spacer()

                        Button("清空已完成") {
                            manager.clearCompleted()
                        }
                        .buttonStyle(PressableButtonStyle())
                        .lightButton()
                        .disabled(manager.tasks.allSatisfy { $0.status != .completed })
                    }
                }
            }
            .padding(24)
        }
        .background(LightTheme.canvas)
    }

    // MARK: - Appearance

    private var appearanceTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                pageTitle("外观", subtitle: "主题色会应用到标记、按钮、进度条与焦点描边；状态色仍保持语义。")

                card {
                    VStack(alignment: .leading, spacing: 12) {
                        cardHeader("主题色", subtitle: "低饱和、可读性优先的预设色板。")

                        LazyVGrid(
                            columns: [GridItem(.adaptive(minimum: 132), spacing: 10)],
                            spacing: 10
                        ) {
                            ForEach(AccentTheme.allCases) { accent in
                                accentOption(accent)
                            }
                        }
                    }
                }

                card {
                    VStack(alignment: .leading, spacing: 12) {
                        cardHeader("纸张底色", subtitle: "只改变画布与控件底色，不改变正文对比度。")

                        HStack(spacing: 10) {
                            ForEach(CanvasTone.allCases) { tone in
                                canvasOption(tone)
                            }
                        }
                    }
                }

                card {
                    VStack(alignment: .leading, spacing: 12) {
                        cardHeader("预览", subtitle: "当前色板在真实组件上的效果。")

                        HStack(spacing: 14) {
                            LiteParseMark(size: 44)

                            VStack(alignment: .leading, spacing: 4) {
                                Text("文献，即刻重构。")
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundStyle(LightTheme.textPrimary)

                                Text("本地识别 · 原始 PDF 不出本机")
                                    .font(.system(size: 11))
                                    .foregroundStyle(LightTheme.textSecondary)
                            }

                            Spacer(minLength: 8)

                            Button("示例操作") {}
                                .buttonStyle(PressableButtonStyle())
                                .lightButton(isProminent: true)
                        }
                        .padding(14)
                        .background(
                            LightTheme.heroGradient,
                            in: RoundedRectangle(cornerRadius: 12, style: .continuous)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(LightTheme.border, lineWidth: 1)
                        )

                        HStack {
                            Text("当前：\(settings.accent.title) · \(settings.canvasTone.title)")
                                .font(.system(size: 11))
                                .foregroundStyle(LightTheme.textMuted)

                            Spacer()

                            Button("恢复默认外观") {
                                settings.resetAppearance()
                            }
                            .buttonStyle(PressableButtonStyle())
                            .lightButton()
                        }
                    }
                }
            }
            .padding(24)
        }
        .background(LightTheme.canvas)
    }

    private func accentOption(_ accent: AccentTheme) -> some View {
        let isSelected = settings.accent == accent

        return Button {
            settings.accent = accent
        } label: {
            HStack(spacing: 8) {
                Circle()
                    .fill(accent.swatch)
                    .frame(width: 16, height: 16)
                    .overlay(Circle().stroke(Color.white.opacity(0.35), lineWidth: 1))

                VStack(alignment: .leading, spacing: 2) {
                    Text(accent.title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(LightTheme.textPrimary)

                    Text(accent.subtitle)
                        .font(.system(size: 10.5))
                        .foregroundStyle(LightTheme.textMuted)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)

                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(accent.swatch)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 9)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                isSelected ? accent.swatch.opacity(0.08) : LightTheme.canvas.opacity(0.55),
                in: RoundedRectangle(cornerRadius: 9, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .stroke(
                        isSelected ? accent.swatch.opacity(0.45) : LightTheme.hairline,
                        lineWidth: isSelected ? 1.2 : 1
                    )
            )
            .contentShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
        .buttonStyle(.plain)
        .help("\(accent.title) — \(accent.subtitle)")
    }

    private func canvasOption(_ tone: CanvasTone) -> some View {
        let isSelected = settings.canvasTone == tone

        return Button {
            settings.canvasTone = tone
        } label: {
            VStack(alignment: .leading, spacing: 7) {
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(tone.palette.top)
                    .frame(height: 36)
                    .overlay(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .stroke(LightTheme.hairline, lineWidth: 1)
                    )
                    .overlay(alignment: .topTrailing) {
                        if isSelected {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(LightTheme.accentBlue)
                                .padding(5)
                        }
                    }

                Text(tone.title)
                    .font(.system(size: 11.5, weight: .semibold))
                    .foregroundStyle(LightTheme.textPrimary)

                Text(tone.subtitle)
                    .font(.system(size: 10.5))
                    .foregroundStyle(LightTheme.textMuted)
                    .lineLimit(1)
            }
            .padding(9)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                isSelected ? LightTheme.accentBlue.opacity(0.06) : LightTheme.cardBg,
                in: RoundedRectangle(cornerRadius: 10, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(
                        isSelected ? LightTheme.accentBlue.opacity(0.40) : LightTheme.hairline,
                        lineWidth: isSelected ? 1.2 : 1
                    )
            )
            .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
        .help("\(tone.title) — \(tone.subtitle)")
    }

    // MARK: - About

    private var aboutTab: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 10)

            LiteParseMark(size: 64)

            VStack(spacing: 4) {
                Text("LiteParse Studio")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(LightTheme.textPrimary)

                Text("版本 \(appVersion)")
                    .font(.system(size: 11.5))
                    .foregroundStyle(LightTheme.textSecondary)
            }

            Text("版面识别与排版在本机完成，原始 PDF 不上传。\n在线翻译会把提取的文字发送至所选服务。")
                .font(.system(size: 12))
                .foregroundStyle(LightTheme.textSecondary)
                .multilineTextAlignment(.center)
                .lineSpacing(3)

            Spacer(minLength: 10)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(32)
        .background(LightTheme.canvas)
    }

    // MARK: - Building blocks

    private func pageTitle(_ title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(LightTheme.textPrimary)

            Text(subtitle)
                .font(.system(size: 11.5))
                .foregroundStyle(LightTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                LightTheme.cardBg,
                in: RoundedRectangle(cornerRadius: 14, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(LightTheme.border, lineWidth: 1)
            )
            .shadow(color: LightTheme.shadowColor, radius: 8, y: 2)
    }

    private func cardHeader(_ title: String, subtitle: String?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(LightTheme.textPrimary)

            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundStyle(LightTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func settingRow<Control: View>(
        title: String,
        detail: String,
        @ViewBuilder control: () -> Control
    ) -> some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 12.5, weight: .medium))
                    .foregroundStyle(LightTheme.textPrimary)

                Text(detail)
                    .font(.system(size: 11))
                    .foregroundStyle(LightTheme.textMuted)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 8)
            control()
        }
    }

    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "2.0.0"
    }

    // MARK: - Actions

    private func chooseOutputFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "设为输出文件夹"
        panel.message = "选择 Studio 新任务的交付物保存位置"

        let current = URL(fileURLWithPath: manager.outputFolderPath)
        if FileManager.default.fileExists(atPath: current.path) {
            panel.directoryURL = current
        }

        guard panel.runModal() == .OK, let selected = panel.url else { return }
        settings.outputFolderPath = selected.path
        manager.syncOutputFolderIfNeeded(force: true)
    }
}

private enum SettingsTab: Hashable {
    case general
    case appearance
    case about
}
