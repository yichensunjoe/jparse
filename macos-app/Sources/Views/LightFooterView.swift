import SwiftUI

public struct LightFooterView: View {
    @ObservedObject var manager: BackendManager
    @State private var clearHovered = false
    @State private var refreshHovered = false

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        let completedCount = manager.tasks.filter { $0.status == .completed }.count
        let activeCount = manager.tasks.filter {
            $0.status == .processing || $0.status == .probing || $0.status == .queued
        }.count

        HStack(spacing: 12) {
            Text("识别与排版在本机完成")
                .font(.system(size: 11))
                .foregroundStyle(LightTheme.textSecondary)

            Spacer()

            HStack(spacing: 12) {
                if activeCount > 0 {
                    HStack(spacing: 5) {
                        Circle()
                            .fill(LightTheme.accentBlue)
                            .frame(width: 5, height: 5)

                        Text("\(activeCount) 项转换中")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(LightTheme.accentBlue)
                            .monospacedDigit()
                            .contentTransition(.numericText())
                    }
                    .help("正在处理的任务数量")
                }

                if !manager.tasks.isEmpty {
                    Text("总计 \(manager.tasks.count) · 已完成 \(completedCount)")
                        .font(.system(size: 11))
                        .foregroundStyle(LightTheme.textSecondary)
                        .monospacedDigit()
                        .contentTransition(.numericText())
                }

                if completedCount > 0 {
                    Button {
                        withAnimation(.smooth(duration: 0.30)) {
                            manager.clearCompleted()
                        }
                    } label: {
                        Text("清空已完成")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(clearHovered ? LightTheme.accentRed : LightTheme.textSecondary)
                    }
                    .buttonStyle(PressableButtonStyle(pressedScale: 0.95))
                    .onHover { hovering in
                        withAnimation(.smooth(duration: 0.16)) { clearHovered = hovering }
                    }
                    .opacity(clearHovered ? 1.0 : 0.8)
                    .help("从列表中移除已完成记录（⌘K）")
                }

                Button {
                    manager.refreshTasks()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(refreshHovered ? LightTheme.textPrimary : LightTheme.textSecondary)
                        .rotationEffect(.degrees(refreshHovered ? 90 : 0))
                        .frame(width: 24, height: 24)
                        .background(
                            Circle().fill(refreshHovered ? Color.black.opacity(0.05) : Color.clear)
                        )
                        .contentShape(Circle())
                }
                .buttonStyle(PressableButtonStyle(pressedScale: 0.9))
                .accessibilityLabel("刷新任务列表")
                .help("刷新任务列表（⌘R）")
                .onHover { hovering in
                    withAnimation(.spring(response: 0.32, dampingFraction: 0.72)) {
                        refreshHovered = hovering
                    }
                }
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 7)
        .background(.regularMaterial)
        .overlay(alignment: .top) {
            LightTheme.hairlineGradient.frame(height: 1)
        }
    }
}
