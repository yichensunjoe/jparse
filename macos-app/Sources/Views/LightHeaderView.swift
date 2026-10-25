import SwiftUI

public struct LightHeaderView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        HStack(spacing: 16) {
            // Left: Brand
            HStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(
                            LinearGradient(
                                colors: [LightTheme.accentBlue, Color(red: 0.25, green: 0.55, blue: 1.0)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 28, height: 28)

                    Image(systemName: "sparkles.rectangle.stack.fill")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(.white)
                }

                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 6) {
                        Text("LiteParse Studio")
                            .font(.system(size: 14, weight: .bold, design: .rounded))
                            .foregroundStyle(LightTheme.textPrimary)

                        Text("2.0")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundStyle(LightTheme.accentBlue)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1.5)
                            .background(LightTheme.accentBlue.opacity(0.10), in: Capsule())
                    }

                    Text("双轨学术文献重构工作台")
                        .font(.system(size: 10))
                        .foregroundStyle(LightTheme.textSecondary)
                }
            }

            Spacer()

            // Center: Raycast / Linear Segmented Control
            HStack(spacing: 3) {
                ForEach(PipelineMode.allCases) { mode in
                    let isSelected = manager.selectedPipeline == mode

                    Button {
                        withAnimation(.spring(response: 0.25, dampingFraction: 0.75)) {
                            manager.selectedPipeline = mode
                        }
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: mode.iconName)
                                .font(.system(size: 10, weight: .medium))
                            Text(mode.shortTitle)
                                .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                        }
                        .foregroundStyle(isSelected ? LightTheme.textPrimary : LightTheme.textSecondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(
                            isSelected ? LightTheme.pillActiveBg : Color.clear,
                            in: RoundedRectangle(cornerRadius: 6)
                        )
                        .shadow(color: isSelected ? Color.black.opacity(0.06) : Color.clear, radius: 2, y: 1)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(3)
            .background(LightTheme.controlBg, in: RoundedRectangle(cornerRadius: 8))

            Spacer()

            // Right: Status indicator & Actions
            HStack(spacing: 8) {
                // Connection Indicator
                HStack(spacing: 5) {
                    Circle()
                        .fill(manager.connectionStatus.indicatorColor)
                        .frame(width: 6, height: 6)
                    Text("本地引擎就绪")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(LightTheme.textSecondary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 5)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 6))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(LightTheme.border, lineWidth: 1.0)
                )

                // Inbox Button
                Button {
                    manager.revealInbox()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "tray.and.arrow.down")
                            .font(.system(size: 10))
                        Text("投递箱")
                    }
                }
                .buttonStyle(.plain)
                .lightButton()

                // Outbox Button
                Button {
                    manager.revealOutbox()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "folder.fill")
                            .font(.system(size: 10))
                        Text("打开成果目录")
                        Image(systemName: "arrow.up.right")
                            .font(.system(size: 8))
                    }
                }
                .buttonStyle(.plain)
                .lightButton(isProminent: true)
            }
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 12)
        .background(Color.white)
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundStyle(LightTheme.border),
            alignment: .bottom
        )
    }
}
