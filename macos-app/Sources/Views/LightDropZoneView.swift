import SwiftUI
import UniformTypeIdentifiers

public struct LightDropZoneView: View {
    @ObservedObject var manager: BackendManager
    /// 无任务时是大尺寸 Hero（承接空状态），有任务时收成一条轻量投递条。
    var isHero: Bool = false

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isTargeted = false
    @State private var isHovering = false
    @State private var breathe: Double = 0.0

    public init(manager: BackendManager, isHero: Bool = false) {
        self.manager = manager
        self.isHero = isHero
    }

    public var body: some View {
        Group {
            if isHero { hero } else { compactBar }
        }
        .onChange(of: isTargeted) { _, targeted in
            breathe = 0
            if targeted && !reduceMotion {
                withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
                    breathe = 0.045
                }
            }
        }
        .dropDestination(for: URL.self) { urls, _ in
            manager.handleDroppedURLs(urls)
            return true
        } isTargeted: { targeted in
            withAnimation(.smooth(duration: 0.22)) {
                isTargeted = targeted
            }
        }
    }

    // MARK: - Hero

    private var hero: some View {
        VStack(spacing: 22) {
            appMark

            VStack(spacing: 9) {
                Text("添加文献，开始处理")
                    .font(.system(size: 26, weight: .semibold))
                    .tracking(-0.4)
                    .foregroundStyle(LightTheme.textPrimary)

                Text("添加 PDF 或文件夹，识别、翻译并生成阅读成果。")
                    .font(.system(size: 13))
                    .foregroundStyle(LightTheme.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)
            }

            HStack(spacing: 10) {
                Button {
                    selectFiles()
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "plus")
                            .font(.system(size: 10, weight: .bold))
                        Text("选取文献")
                    }
                }
                .buttonStyle(PressableButtonStyle())
                .lightButton(isProminent: true)
                .help("选择一个或多个 PDF")

                Button {
                    selectFolder()
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "folder")
                            .font(.system(size: 10, weight: .medium))
                        Text("导入目录")
                    }
                }
                .buttonStyle(PressableButtonStyle())
                .lightButton()
                .help("导入整个文件夹中的 PDF")
            }

            HStack(spacing: 5) {
                Image(systemName: "hand.draw")
                    .font(.system(size: 10, weight: .medium))
                Text(isTargeted ? "松开即可投递" : "也可以把文件拖到窗口任意位置")
                    .font(.system(size: 11))
            }
            .foregroundStyle(isTargeted ? LightTheme.accentBlue : LightTheme.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 24)
        .padding(.vertical, 50)
        .background {
            ZStack {
                RoundedRectangle(cornerRadius: LightTheme.radiusHero, style: .continuous)
                    .fill(LightTheme.heroGradient)

                RoundedRectangle(cornerRadius: LightTheme.radiusHero, style: .continuous)
                    .fill(
                        RadialGradient(
                            colors: [
                                LightTheme.accentBlue.opacity(isTargeted ? 0.10 : 0.055),
                                Color.clear
                            ],
                            center: .top,
                            startRadius: 0,
                            endRadius: 420
                        )
                    )

                RoundedRectangle(cornerRadius: LightTheme.radiusHero, style: .continuous)
                    .fill(
                        RadialGradient(
                            colors: [
                                LightTheme.accentCyan.opacity(0.035),
                                Color.clear
                            ],
                            center: .bottomTrailing,
                            startRadius: 0,
                            endRadius: 380
                        )
                    )

                if isTargeted {
                    RoundedRectangle(cornerRadius: LightTheme.radiusHero, style: .continuous)
                        .fill(LightTheme.accentBlue.opacity(breathe))
                }
            }
        }
        .overlay(
            RoundedRectangle(cornerRadius: LightTheme.radiusHero, style: .continuous)
                .strokeBorder(
                    isTargeted ? LightTheme.accentBlue.opacity(0.55) : LightTheme.border,
                    lineWidth: isTargeted ? 1.5 : 1
                )
        )
        .shadow(color: LightTheme.shadowColor, radius: isHovering ? 22 : 16, y: isHovering ? 8 : 5)
        .onHover { hovering in
            withAnimation(.smooth(duration: 0.25)) { isHovering = hovering }
        }
    }

    private var appMark: some View {
        JParseMark(size: 56)
            .scaleEffect(isTargeted ? 1.05 : 1.0)
            .animation(.spring(response: 0.34, dampingFraction: 0.72), value: isTargeted)
    }

    // MARK: - Compact Bar

    private var compactBar: some View {
        HStack(spacing: 13) {
            ZStack {
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(LightTheme.accentBlue.opacity(isTargeted ? 0.9 : 0.10))
                    .frame(width: 34, height: 34)

                Image(systemName: isTargeted ? "arrow.down.doc.fill" : "doc.on.doc.fill")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(isTargeted ? .white : LightTheme.accentBlue)
                    .contentTransition(.symbolEffect(.replace))
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(isTargeted ? "松开即可投递" : "拖放 PDF 到窗口任意位置")
                    .font(.system(size: 12.5, weight: .semibold))
                    .foregroundStyle(isTargeted ? LightTheme.accentBlue : LightTheme.textPrimary)

                Text("智能双轨自动解析 · 支持多文件或目录投递")
                    .font(.system(size: 11))
                    .foregroundStyle(LightTheme.textSecondary)
            }

            Spacer(minLength: 8)

            HStack(spacing: 8) {
                Button {
                    selectFiles()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "plus")
                            .font(.system(size: 9.5, weight: .bold))
                        Text("选取文献")
                    }
                }
                .buttonStyle(PressableButtonStyle())
                .lightButton(isProminent: true)
                .help("选择一个或多个 PDF")

                Button {
                    selectFolder()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "folder")
                            .font(.system(size: 11, weight: .medium))
                        Text("导入目录")
                    }
                }
                .buttonStyle(PressableButtonStyle())
                .lightButton()
                .help("导入整个文件夹中的 PDF")
            }
        }
        .padding(.horizontal, 15)
        .padding(.vertical, 11)
        .background(
            isTargeted ? LightTheme.accentBlue.opacity(0.05) : LightTheme.cardBg,
            in: RoundedRectangle(cornerRadius: LightTheme.radiusCard, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: LightTheme.radiusCard, style: .continuous)
                .strokeBorder(
                    isTargeted ? LightTheme.accentBlue.opacity(0.55) : LightTheme.border,
                    lineWidth: isTargeted ? 1.5 : 1
                )
        )
        .shadow(color: LightTheme.shadowColor, radius: 6, y: 2)
    }

    // MARK: - Pickers

    private func selectFiles() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.pdf]
        panel.prompt = "添加至转换队列"

        if panel.runModal() == .OK {
            manager.handleDroppedURLs(panel.urls)
        }
    }

    private func selectFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = true
        panel.prompt = "导入整套文献"

        if panel.runModal() == .OK {
            manager.handleDroppedURLs(panel.urls)
        }
    }
}
