import SwiftUI

public struct GlassHeaderView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        HStack(spacing: 16) {
            // Brand Logo & Title
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(
                            LinearGradient(
                                colors: [Color.blue, Color.cyan],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 36, height: 36)

                    Image(systemName: "sparkles.rectangle.stack.fill")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundStyle(.white)
                }

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text("LiteParse Studio")
                            .font(.system(size: 16, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)

                        Text("Liquid Glass")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(Color.cyan)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .glassEffect(.regular.tint(Color.cyan.opacity(0.2)), in: .capsule)
                    }

                    Text("双轨文献智能重构 · 纯图片/扫描件出版级高清 PDF 生成平台")
                        .font(.system(size: 11))
                        .foregroundStyle(Color(white: 0.60))
                }
            }

            Spacer()

            // Connection Status Capsule
            HStack(spacing: 6) {
                Circle()
                    .fill(manager.connectionStatus.indicatorColor)
                    .frame(width: 7, height: 7)

                Text(manager.connectionStatus.statusText)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Color(white: 0.85))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .glassEffect(
                .regular.tint(manager.connectionStatus.indicatorColor.opacity(0.15)),
                in: .capsule
            )

            // Header Action Buttons
            HStack(spacing: 8) {
                Button {
                    manager.revealInbox()
                } label: {
                    Label("投递箱", systemImage: "tray.and.arrow.down.fill")
                        .font(.system(size: 12, weight: .medium))
                }
                .buttonStyle(.glass)

                Button {
                    manager.revealOutbox()
                } label: {
                    Label("打开输出目录", systemImage: "folder.fill")
                        .font(.system(size: 12, weight: .medium))
                }
                .buttonStyle(.glassProminent)
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
        .glassEffect(
            .regular.tint(Color.black.opacity(0.25)),
            in: .rect(cornerRadius: 16)
        )
    }
}
