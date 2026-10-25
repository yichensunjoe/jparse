import SwiftUI
import UniformTypeIdentifiers

public struct SwissDropRailView: View {
    @ObservedObject var manager: BackendManager
    @State private var isTargeted = false
    @State private var isHovering = false

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        HStack(spacing: 16) {
            // Icon & Technical prompt
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 6)
                        .fill(isTargeted ? SwissTheme.accentCobalt.opacity(0.2) : SwissTheme.surfaceBg)
                        .frame(width: 44, height: 44)

                    Image(systemName: isTargeted ? "arrow.down.doc.fill" : "doc.badge.plus")
                        .font(.system(size: 20))
                        .foregroundStyle(isTargeted ? SwissTheme.accentCobalt : SwissTheme.textSecondary)
                }

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text(isTargeted ? "松开鼠标即可投递文献" : "拖入 PDF 文献或文献文件夹")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(isTargeted ? SwissTheme.accentCobalt : SwissTheme.textPrimary)

                        Text("AUTO DECOMPOSITION")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(SwissTheme.textMuted)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(SwissTheme.surfaceBg, in: RoundedRectangle(cornerRadius: 4))
                    }

                    Text("支持 MDPI / IEEE 现代矢量论文与历史古籍扫描件 · 自动多级目录深度提取")
                        .font(.system(size: 11))
                        .foregroundStyle(SwissTheme.textSecondary)
                }
            }

            Spacer()

            // Swiss action buttons
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
                .swissButton(isProminent: isTargeted)

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
                .swissButton()
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(
            isTargeted ? SwissTheme.surfaceBg.opacity(0.8) : SwissTheme.surfaceBg.opacity(0.35),
            in: RoundedRectangle(cornerRadius: 8)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(
                    isTargeted ? SwissTheme.accentCobalt : SwissTheme.hairline,
                    style: StrokeStyle(lineWidth: 1.0, dash: isTargeted ? [] : [4, 4])
                )
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
        panel.prompt = "投递至工作台"

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
