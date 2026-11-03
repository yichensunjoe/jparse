import SwiftUI

public struct LightHeaderView: View {
    @ObservedObject var manager: BackendManager
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.openSettings) private var openSettings
    @State private var pulse = false
    @State private var isCompact = false
    @State private var inboxHovered = false
    @State private var settingsHovered = false

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        HStack(spacing: isCompact ? 10 : 16) {
            brand
            Spacer(minLength: 8)
            statusAndActions
        }
        // 标题栏与红绿灯同排：左侧留出 78pt 给窗口按钮，像 Finder / 备忘录。
        .padding(.leading, 78)
        .padding(.trailing, isCompact ? 16 : 20)
        .padding(.top, 5)
        .padding(.bottom, 10)
        .onGeometryChange(for: Bool.self) { proxy in
            proxy.size.width < 1020
        } action: { compact in
            withAnimation(.smooth(duration: 0.28)) {
                isCompact = compact
            }
        }
        .background(.regularMaterial)
        .overlay(alignment: .bottom) {
            LightTheme.hairlineGradient.frame(height: 1)
        }
    }

    // MARK: - Brand

    private var brand: some View {
        HStack(spacing: 9) {
            JParseMark(size: 26)

            HStack(spacing: 4) {
                Text("JParse")
                    .font(.system(size: 13.5, weight: .semibold))
                    .foregroundStyle(LightTheme.textPrimary)
                Text("Studio")
                    .font(.system(size: 13.5, weight: .regular))
                    .foregroundStyle(LightTheme.textSecondary)
            }
            .lineLimit(1)
        }
    }


    private func startPulseIfConnected() {
        guard !reduceMotion, manager.connectionStatus.isConnected, !pulse else { return }
        withAnimation(.easeOut(duration: 2.0).repeatForever(autoreverses: false)) {
            pulse = true
        }
    }

    // MARK: - Status & Actions

    private var statusAndActions: some View {
        HStack(spacing: isCompact ? 8 : 10) {
            HStack(spacing: 5) {
                ZStack {
                    Circle()
                        .fill(manager.connectionStatus.indicatorColor)
                        .frame(width: 6, height: 6)

                    Circle()
                        .stroke(manager.connectionStatus.indicatorColor.opacity(0.40), lineWidth: 1.2)
                        .frame(width: 6, height: 6)
                        .scaleEffect(pulse ? 2.4 : 1.0)
                        .opacity(pulse ? 0.0 : 1.0)
                }
                .onAppear { startPulseIfConnected() }
                .onChange(of: manager.connectionStatus) { _, _ in startPulseIfConnected() }

                Text(isCompact ? manager.connectionStatus.compactLabel : manager.connectionStatus.shortLabel)
                    .font(.system(size: 11.5, weight: .medium))
                    .foregroundStyle(LightTheme.textSecondary)
                    .lineLimit(1)
                    .fixedSize()
            }
            .padding(.horizontal, isCompact ? 2 : 4)
            .help(manager.connectionStatus.statusText)
            .accessibilityElement(children: .combine)

            // 次要操作：圆形图标按钮，悬停才浮出底色。
            Button {
                manager.revealInbox()
            } label: {
                Image(systemName: "tray")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(LightTheme.textSecondary)
                    .frame(width: 28, height: 28)
                    .background(
                        Circle().fill(inboxHovered ? Color.black.opacity(0.05) : Color.clear)
                    )
                    .contentShape(Circle())
            }
            .buttonStyle(PressableButtonStyle(pressedScale: 0.92))
            .onHover { hovering in
                withAnimation(.smooth(duration: 0.18)) { inboxHovered = hovering }
            }
            .help("在访达中打开投递箱（⌘⇧I）")
            .accessibilityLabel("打开投递箱")

            Button {
                manager.revealOutbox()
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "folder.fill")
                        .font(.system(size: 10, weight: .semibold))
                    Text(isCompact ? "成果目录" : "打开成果目录")
                        .lineLimit(1)
                        .fixedSize()
                }
            }
            .buttonStyle(PressableButtonStyle())
            .lightButton()
            .help("在访达中打开成果目录（⌘⇧O）")

            Button {
                openSettings()
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(LightTheme.textSecondary)
                    .frame(width: 28, height: 28)
                    .background(
                        Circle().fill(settingsHovered ? Color.black.opacity(0.05) : Color.clear)
                    )
                    .contentShape(Circle())
            }
            .buttonStyle(PressableButtonStyle(pressedScale: 0.92))
            .onHover { hovering in
                withAnimation(.smooth(duration: 0.18)) { settingsHovered = hovering }
            }
            .help("设置（⌘,）")
            .accessibilityLabel("设置")
        }
    }
}
