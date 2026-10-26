import SwiftUI

public struct LightFooterView: View {
    @ObservedObject var manager: BackendManager
    @State private var clearHovered = false

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        let completedCount = manager.tasks.filter { $0.status == .completed }.count
        let processingCount = manager.tasks.filter { $0.status == .processing || $0.status == .probing || $0.status == .queued }.count

        HStack(spacing: 14) {
            // Privacy assurance — friendlier copy
            HStack(spacing: 5) {
                Image(systemName: "checkmark.shield.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(LightTheme.accentGreen.opacity(0.8))

                Text("100% 本地离线 · 数据不出本机")
                    .font(.system(size: 11))
                    .foregroundStyle(LightTheme.textMuted)
            }

            Spacer()

            // Active counts & actions
            HStack(spacing: 10) {
                if processingCount > 0 {
                    HStack(spacing: 4) {
                        ProgressView()
                            .controlSize(.mini)
                        Text("\(processingCount) 项转换中")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(LightTheme.accentBlue)
                    }
                }

                Text("总计 \(manager.tasks.count) 丨已完成 \(completedCount)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(LightTheme.textMuted)

                if completedCount > 0 {
                    Button {
                        withAnimation {
                            manager.clearCompleted()
                        }
                    } label: {
                        Text("清空完成")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(clearHovered ? LightTheme.accentRed : LightTheme.textMuted)
                    }
                    .buttonStyle(.plain)
                    .onHover { h in clearHovered = h }
                    .opacity(clearHovered ? 1.0 : 0.7)
                }

                Button {
                    manager.refreshTasks()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11))
                        .foregroundStyle(LightTheme.textMuted)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 8)
        .background(LightTheme.cardBg)
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundStyle(LightTheme.border),
            alignment: .top
        )
    }
}
