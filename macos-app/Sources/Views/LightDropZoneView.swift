import SwiftUI
import UniformTypeIdentifiers

public struct LightDropZoneView: View {
    @ObservedObject var manager: BackendManager
    @State private var isTargeted = false
    @State private var isHovering = false

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        HStack(spacing: 18) {
            // Icon
            ZStack {
                Circle()
                    .fill(isTargeted ? LightTheme.accentBlue.opacity(0.12) : LightTheme.controlBg.opacity(0.8))
                    .frame(width: 48, height: 48)

                Image(systemName: isTargeted ? "arrow.down.doc.fill" : "doc.viewfinder")
                    .font(.system(size: 22))
                    .foregroundStyle(isTargeted ? LightTheme.accentBlue : LightTheme.textSecondary)
                    .scaleEffect(isTargeted ? 1.15 : 1.0)
                    .animation(.spring(response: 0.3, dampingFraction: 0.65), value: isTargeted)
            }

            // Headline & Description
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 8) {
                    Text(isTargeted ? "松开鼠标即可投递文献" : "拖放 PDF 文献或文献文件夹至此处")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                        .foregroundStyle(isTargeted ? LightTheme.accentBlue : LightTheme.textPrimary)

                    Text("支持多层级目录递归")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(LightTheme.textMuted)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(LightTheme.controlBg, in: Capsule())
                }

                Text("自动智能分流：现代矢量论文走 pdf2zh 出版级重排，历史扫描专著走 OpenDataLoader 高清重构")
                    .font(.system(size: 12))
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
        .padding(.horizontal, 20)
        .padding(.vertical, 18)
        .background(
            isTargeted ? Color(red: 0.94, green: 0.97, blue: 1.0) : Color.white,
            in: RoundedRectangle(cornerRadius: 12)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(
                    isTargeted ? LightTheme.accentBlue : LightTheme.border,
                    lineWidth: isTargeted ? 2.0 : 1.0
                )
        )
        .shadow(
            color: isTargeted ? LightTheme.accentBlue.opacity(0.12) : LightTheme.shadowColor,
            radius: isTargeted ? 8 : 4,
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
