import SwiftUI

public struct LightFooterView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        let completedCount = manager.tasks.filter { $0.status == .completed }.count
        let processingCount = manager.tasks.filter { $0.status == .processing || $0.status == .probing || $0.status == .queued }.count

        HStack(spacing: 16) {
            // Privacy assurance
            HStack(spacing: 6) {
                Image(systemName: "checkmark.shield.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(LightTheme.accentGreen)

                Text("100% 本地离线处理 · 零云端留存 · 确定性原子替换")
                    .font(.system(size: 11))
                    .foregroundStyle(LightTheme.textSecondary)
            }

            Spacer()

            // Active counts & actions
            HStack(spacing: 12) {
                if processingCount > 0 {
                    HStack(spacing: 5) {
                        ProgressView()
                            .controlSize(.mini)
                        Text("\(processingCount) 项转换中")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(LightTheme.accentBlue)
                    }
                }

                Text("总计 \(manager.tasks.count) 项 · 已完成 \(completedCount) 项")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(LightTheme.textSecondary)

                if completedCount > 0 {
                    Button {
                        withAnimation {
                            manager.clearCompleted()
                        }
                    } label: {
                        Text("清空完成")
                    }
                    .buttonStyle(.plain)
                    .lightButton()
                }

                Button {
                    manager.refreshTasks()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .lightButton()
            }
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 10)
        .background(Color.white)
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundStyle(LightTheme.border),
            alignment: .top
        )
    }
}
