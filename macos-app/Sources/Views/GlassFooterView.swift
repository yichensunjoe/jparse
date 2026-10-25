import SwiftUI

public struct GlassFooterView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        let completedCount = manager.tasks.filter { $0.status == .completed }.count
        let failedCount = manager.tasks.filter { $0.status == .failed }.count
        let processingCount = manager.tasks.filter { $0.status == .processing || $0.status == .probing || $0.status == .queued }.count

        HStack(spacing: 16) {
            // Left: Privacy & Architecture Guarantee
            HStack(spacing: 8) {
                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.green)

                Text("100% 本地安全处理 · 零云端上传 · 确定性原子写入")
                    .font(.system(size: 11))
                    .foregroundStyle(Color(white: 0.65))
            }

            Spacer()

            // Center / Right: Task Counters
            HStack(spacing: 12) {
                if processingCount > 0 {
                    HStack(spacing: 4) {
                        ProgressView()
                            .controlSize(.mini)
                        Text("\(processingCount) 项转换中")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Color.cyan)
                    }
                }

                Text("总计 \(manager.tasks.count) 项 · 已完成 \(completedCount) 项\(failedCount > 0 ? " · 异常 \(failedCount) 项" : "")")
                    .font(.system(size: 11))
                    .foregroundStyle(Color(white: 0.60))

                if completedCount > 0 {
                    Button {
                        withAnimation {
                            manager.clearCompleted()
                        }
                    } label: {
                        Text("清除已完成")
                            .font(.system(size: 11))
                    }
                    .buttonStyle(.glass)
                }

                Button {
                    manager.refreshTasks()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11))
                }
                .buttonStyle(.glass)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .glassEffect(
            .regular.tint(Color.black.opacity(0.20)),
            in: .rect(cornerRadius: 14)
        )
    }
}
