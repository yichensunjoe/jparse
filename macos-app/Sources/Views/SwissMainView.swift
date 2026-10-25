import SwiftUI

public struct SwissMainView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Top Bar
            HStack(spacing: 12) {
                HStack(spacing: 6) {
                    Text("WORKSPACE")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(SwissTheme.accentCobalt)
                    Text("/")
                        .foregroundStyle(SwissTheme.textMuted)
                    Text("文献重构流水线")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(SwissTheme.textPrimary)
                }

                Spacer()

                // Upload indicator
                if manager.isUploading {
                    HStack(spacing: 6) {
                        ProgressView()
                            .controlSize(.mini)
                        Text(manager.uploadStatusMessage)
                            .font(.system(size: 11))
                            .foregroundStyle(SwissTheme.accentCobalt)
                    }
                }

                // Stats chip
                let done = manager.tasks.filter { $0.status == .completed }.count
                Text("共 \(manager.tasks.count) 项 · 已完成 \(done) 项")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(SwissTheme.textSecondary)

                Button {
                    manager.refreshTasks()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .swissButton()
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 14)
            .background(SwissTheme.canvasBg)

            Divider()
                .background(SwissTheme.hairline)

            // Main Content Area
            ScrollView(.vertical, showsIndicators: true) {
                VStack(alignment: .leading, spacing: 16) {
                    // 1. Sleek Drop Rail
                    SwissDropRailView(manager: manager)

                    // 2. Error message banner if any
                    if let err = manager.errorMessage {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(SwissTheme.accentAmber)
                            Text(err)
                                .font(.system(size: 12))
                                .foregroundStyle(SwissTheme.textPrimary)
                            Spacer()
                            Button {
                                manager.errorMessage = nil
                            } label: {
                                Image(systemName: "xmark")
                                    .font(.system(size: 10))
                                    .foregroundStyle(SwissTheme.textMuted)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(10)
                        .background(SwissTheme.accentAmber.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(SwissTheme.accentAmber.opacity(0.3), lineWidth: 1.0)
                        )
                    }

                    // 3. Queue Header
                    HStack(alignment: .firstTextBaseline) {
                        Text("文献队列")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(SwissTheme.textPrimary)

                        Text("QUEUE (\(manager.tasks.count))")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundStyle(SwissTheme.textMuted)

                        Spacer()
                    }
                    .padding(.top, 4)

                    // 4. Tasks list or Minimal Empty State
                    if manager.tasks.isEmpty {
                        emptyStateView
                    } else {
                        LazyVStack(spacing: 8) {
                            ForEach(manager.tasks) { task in
                                SwissTaskRowView(task: task, manager: manager)
                            }
                        }
                    }
                }
                .padding(22)
            }

            Divider()
                .background(SwissTheme.hairline)

            // Bottom subtle status bar
            HStack {
                HStack(spacing: 6) {
                    Circle()
                        .fill(SwissTheme.accentEmerald)
                        .frame(width: 5, height: 5)
                    Text("原子写入保证 · 自动生成中文精译版、双语对照版与原位网页")
                        .font(.system(size: 10))
                        .foregroundStyle(SwissTheme.textMuted)
                }

                Spacer()

                Text("LiteParse 2.0 Swiss Core")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(SwissTheme.textMuted)
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 8)
            .background(SwissTheme.sidebarBg.opacity(0.5))
        }
        .background(SwissTheme.canvasBg)
    }

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "tray")
                .font(.system(size: 28))
                .foregroundStyle(SwissTheme.textMuted.opacity(0.6))

            VStack(spacing: 4) {
                Text("当前队列无任务")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(SwissTheme.textSecondary)

                Text("拖入上方光轨即可立即分流执行")
                    .font(.system(size: 11))
                    .foregroundStyle(SwissTheme.textMuted)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 48)
        .background(SwissTheme.surfaceBg.opacity(0.2), in: RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(SwissTheme.hairline, lineWidth: 1.0)
        )
    }
}
