import SwiftUI
import UniformTypeIdentifiers

public struct LightDropZoneView: View {
    @ObservedObject var manager: BackendManager
    @State private var isTargeted = false
    @State private var isHovering = false
    @State private var breatheOpacity: Double = 0.0

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        HStack(spacing: 16) {
            // Icon — stacked docs style
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(LightTheme.controlBg.opacity(0.5))
                    .frame(width: 28, height: 32)
                    .rotationEffect(.degrees(-6))
                    .offset(x: -2, y: 1)

                RoundedRectangle(cornerRadius: 6)
                    .fill(isTargeted ? LightTheme.accentBlue.opacity(0.15) : LightTheme.controlBg.opacity(0.7))
                    .frame(width: 28, height: 32)

                Image(systemName: isTargeted ? "arrow.down.doc.fill" : "doc.on.doc")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(isTargeted ? LightTheme.accentBlue : LightTheme.textSecondary)
                    .scaleEffect(isTargeted ? 1.12 : 1.0)
                    .animation(.spring(response: 0.3, dampingFraction: 0.65), value: isTargeted)
            }

            // Headline & Description — compact
            VStack(alignment: .leading, spacing: 2) {
                Text(isTargeted ? "松开即可投递" : "拖放 PDF 文献或文件夹至此处")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(isTargeted ? LightTheme.accentBlue : LightTheme.textPrimary)

                Text("智能分流 · 出版级重构")
                    .font(.system(size: 11))
                    .foregroundStyle(LightTheme.textSecondary)
            }

            Spacer()

            // Action Buttons
            HStack(spacing: 8) {
                Button {
                    selectFiles()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "plus")
                            .font(.system(size: 10, weight: .bold))
                        Text("选取文献")
                    }
                }
                .buttonStyle(.plain)
                .lightButton(isProminent: true)

                Button {
                    selectFolder()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "folder")
                            .font(.system(size: 10))
                        Text("导入目录")
                    }
                }
                .buttonStyle(.plain)
                .lightButton()
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 14)
        .background(
            ZStack {
                RoundedRectangle(cornerRadius: LightTheme.radiusCard)
                    .fill(isTargeted ? Color(red: 0.94, green: 0.97, blue: 1.0) : LightTheme.cardBg)

                // Breathe glow when dragging over
                if isTargeted {
                    RoundedRectangle(cornerRadius: LightTheme.radiusCard)
                        .fill(LightTheme.accentBlue.opacity(breatheOpacity))
                        .onAppear {
                            withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                                breatheOpacity = 0.06
                            }
                        }
                        .onDisappear { breatheOpacity = 0.0 }
                }
            }
        )
        .overlay(
            RoundedRectangle(cornerRadius: LightTheme.radiusCard)
                .stroke(
                    isTargeted ? LightTheme.accentBlue : LightTheme.border,
                    lineWidth: isTargeted ? 1.5 : 1.0
                )
        )
        .shadow(
            color: isTargeted ? LightTheme.accentBlue.opacity(0.10) : LightTheme.shadowColor,
            radius: isTargeted ? 8 : 3,
            y: 2
        )
        .onHover { hovering in
            isHovering = hovering
        }
        .dropDestination(for: URL.self) { urls, _ in
            manager.handleDroppedURLs(urls)
            return true
        } isTargeted: { targeted in
            withAnimation(.easeInOut(duration: 0.15)) {
                isTargeted = targeted
            }
        }
    }

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
