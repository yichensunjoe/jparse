import SwiftUI
import UniformTypeIdentifiers

public struct HeroDropZoneView: View {
    @ObservedObject var manager: BackendManager
    @State private var isTargeted = false
    @State private var isHovering = false

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        VStack(spacing: 16) {
            // Icon with glowing liquid gradient
            ZStack {
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                (isTargeted ? Color.blue : Color.cyan).opacity(0.35),
                                Color.clear
                            ],
                            center: .center,
                            startRadius: 5,
                            endRadius: 45
                        )
                    )
                    .frame(width: 80, height: 80)
                    .blur(radius: isTargeted ? 12 : 8)

                Image(systemName: isTargeted ? "arrow.down.doc.fill" : "doc.viewfinder.fill")
                    .font(.system(size: 38, weight: .semibold))
                    .foregroundStyle(
                        LinearGradient(
                            colors: isTargeted
                                ? [Color.cyan, Color.blue]
                                : [Color.white, Color(white: 0.82)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .scaleEffect(isTargeted ? 1.15 : (isHovering ? 1.05 : 1.0))
                    .animation(.spring(response: 0.35, dampingFraction: 0.65), value: isTargeted)
                    .animation(.spring(response: 0.35, dampingFraction: 0.65), value: isHovering)
            }

            // Headline & Description
            VStack(spacing: 6) {
                Text(isTargeted ? "松开鼠标即可投递转换" : "拖放 PDF 文献或文件夹至此处")
                    .font(.system(size: 19, weight: .semibold, design: .rounded))
                    .foregroundStyle(.white)

                Text("支持拖入单份 PDF、多个文件或整套文件夹，自动无限级递归提取并加入转换队列")
                    .font(.system(size: 13, weight: .regular))
                    .foregroundStyle(Color(white: 0.70))
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 480)
            }

            // Action button with Glass styling
            HStack(spacing: 12) {
                Button {
                    selectFiles()
                } label: {
                    Label("选取 PDF 文献", systemImage: "plus.circle.fill")
                        .font(.system(size: 13, weight: .medium))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.glass)

                Button {
                    selectFolder()
                } label: {
                    Label("选取整套文件夹", systemImage: "folder.fill.badge.plus")
                        .font(.system(size: 13, weight: .medium))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.glass)
            }
            .padding(.top, 4)
        }
        .padding(.vertical, 32)
        .padding(.horizontal, 28)
        .frame(maxWidth: .infinity)
        .overlay(
            RoundedRectangle(cornerRadius: 22)
                .stroke(
                    LinearGradient(
                        colors: isTargeted
                            ? [Color.cyan, Color.blue.opacity(0.8)]
                            : [Color.white.opacity(0.20), Color.white.opacity(0.06)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: isTargeted ? 2.0 : 1.0
                )
        )
        // Liquid Glass Surface Modifier: Applied after frame and padding
        .glassEffect(
            .regular
                .tint(isTargeted ? .blue.opacity(0.25) : .white.opacity(0.05))
                .interactive(),
            in: .rect(cornerRadius: 22)
        )
        .scaleEffect(isTargeted ? 1.012 : 1.0)
        .animation(.spring(response: 0.35, dampingFraction: 0.7), value: isTargeted)
        .onHover { hovering in
            isHovering = hovering
        }
        // Native Drag & Drop destination for local file URLs
        .dropDestination(for: URL.self) { urls, _ in
            manager.handleDroppedURLs(urls)
            return true
        } isTargeted: { targeted in
            isTargeted = targeted
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
        panel.prompt = "导入整套目录"

        if panel.runModal() == .OK {
            manager.handleDroppedURLs(panel.urls)
        }
    }
}
