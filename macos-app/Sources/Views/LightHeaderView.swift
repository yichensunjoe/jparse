import SwiftUI

public struct LightHeaderView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        HStack(spacing: 16) {
            // Left: Slim Brand
            HStack(spacing: 9) {
                ZStack {
                    RoundedRectangle(cornerRadius: 7)
                        .fill(
                            LinearGradient(
                                colors: [LightTheme.accentBlue, Color(red: 0.30, green: 0.58, blue: 1.0)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 26, height: 26)

                    Image(systemName: "text.document.fill")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(.white)
                }

                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text("LiteParse Studio")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                        .foregroundStyle(LightTheme.textPrimary)

                    Text("2.0")
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .foregroundStyle(LightTheme.textMuted)
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
                            in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge)
                        )
                        .shadow(color: isSelected ? Color.black.opacity(0.06) : Color.clear, radius: 2, y: 1)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(3)
            .background(LightTheme.controlBg, in: RoundedRectangle(cornerRadius: LightTheme.radiusButton))

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
                .background(LightTheme.cardBg, in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge))
                .overlay(
                    RoundedRectangle(cornerRadius: LightTheme.radiusBadge)
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
        .padding(.vertical, 10)
        .background(LightTheme.cardBg)
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundStyle(LightTheme.border),
            alignment: .bottom
        )
    }
}
