import SwiftUI

public struct TaskCardView: View {
    public let task: TaskItem
    @ObservedObject var manager: BackendManager
    var animationNamespace: Namespace.ID

    @State private var isHovered = false

    public init(task: TaskItem, manager: BackendManager, animationNamespace: Namespace.ID) {
        self.task = task
        self.manager = manager
        self.animationNamespace = animationNamespace
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Header Row: File Icon, Title, Path, Badges
            HStack(alignment: .top, spacing: 12) {
                // Document Icon
                ZStack {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(task.status.tintColor.opacity(0.18))
                        .frame(width: 42, height: 42)

                    Image(systemName: task.status.iconName)
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(task.status.tintColor)
                }

                // File metadata
                VStack(alignment: .leading, spacing: 3) {
                    Text(task.filename)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.white)
                        .lineLimit(1)

                    HStack(spacing: 8) {
                        Text(task.formattedSize)
                            .font(.system(size: 11))
                            .foregroundStyle(Color(white: 0.60))

                        if !task.relative_path.isEmpty && task.relative_path != task.filename {
                            Text("·")
                                .foregroundStyle(Color(white: 0.40))
                            Text(task.relative_path)
                                .font(.system(size: 11))
                                .foregroundStyle(Color(white: 0.60))
                                .lineLimit(1)
                        }

                        if task.duration > 0 {
                            Text("·")
                                .foregroundStyle(Color(white: 0.40))
                            Text(String(format: "用时 %.1fs", task.duration))
                                .font(.system(size: 11))
                                .foregroundStyle(Color.cyan.opacity(0.85))
                        }
                    }
                }

                Spacer()

                // Badges: Doc Type & Status
                HStack(spacing: 8) {
                    if task.doc_type != "unknown" {
                        Text(task.docTypeBadgeText)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(task.docTypeColor)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .glassEffect(
                                .regular.tint(task.docTypeColor.opacity(0.20)),
                                in: .capsule
                            )
                    }

                    Text(task.status.localizedDescription)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(task.status.tintColor)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .glassEffect(
                            .regular.tint(task.status.tintColor.opacity(0.20)),
                            in: .capsule
                        )
                }
            }

            // Progress Bar (when processing or queued)
            if task.status == .probing || task.status == .processing || task.status == .queued {
                VStack(spacing: 6) {
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            // Track
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color.white.opacity(0.08))
                                .frame(height: 6)

                            // Progress Fill
                            RoundedRectangle(cornerRadius: 4)
                                .fill(
                                    LinearGradient(
                                        colors: [Color.cyan, Color.blue],
                                        startPoint: .leading,
                                        endPoint: .trailing
                                    )
                                )
                                .frame(width: max(8, geo.size.width * CGFloat(task.progress) / 100.0), height: 6)
                                .animation(.spring(response: 0.4, dampingFraction: 0.8), value: task.progress)
                        }
                    }
                    .frame(height: 6)

                    HStack {
                        Text(task.status == .probing ? "探测版面拓扑与矢量特征..." : "正在进行原位对齐与神经翻译...")
                            .font(.system(size: 11))
                            .foregroundStyle(Color(white: 0.55))
                        Spacer()
                        Text("\(Int(task.progress))%")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Color.cyan)
                    }
                }
            }

            // Error Message (if failed)
            if let err = task.error, !err.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.octagon.fill")
                        .foregroundStyle(.red)
                    Text(err)
                        .font(.system(size: 12))
                        .foregroundStyle(Color.red.opacity(0.9))
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color.red.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            }

            // Output Deliverables (if completed)
            if task.status == .completed && !task.output_files.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("交付产物（已原子写入 outbox/）:")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Color(white: 0.65))

                    VStack(spacing: 6) {
                        ForEach(task.output_files) { item in
                            outputItemRow(item: item)
                        }
                    }
                }
            }
        }
        .padding(18)
        .overlay(
            RoundedRectangle(cornerRadius: 18)
                .stroke(
                    isHovered
                        ? Color.white.opacity(0.24)
                        : Color.white.opacity(0.08),
                    lineWidth: 1.0
                )
        )
        // Liquid Glass styling
        .glassEffect(
            .regular
                .tint(task.status == .completed ? Color.green.opacity(0.06) : Color.white.opacity(0.04))
                .interactive(),
            in: .rect(cornerRadius: 18)
        )
        .glassEffectID(task.id, in: animationNamespace)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.2)) {
                isHovered = hovering
            }
        }
    }

    @ViewBuilder
    private func outputItemRow(item: OutputFileItem) -> some View {
        HStack(spacing: 10) {
            Image(systemName: item.is_pdf ? "doc.richtext.fill" : "safari.fill")
                .font(.system(size: 14))
                .foregroundStyle(item.is_pdf ? Color.red.opacity(0.85) : Color.blue.opacity(0.85))

            Text(item.name)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Color.white)
                .lineLimit(1)

            if !item.formattedSize.isEmpty {
                Text(item.formattedSize)
                    .font(.system(size: 10))
                    .foregroundStyle(Color(white: 0.50))
            }

            Spacer()

            // Quick Actions
            HStack(spacing: 6) {
                Button {
                    manager.openFile(path: item.path)
                } label: {
                    Label("打开", systemImage: "arrow.up.forward.app")
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.glassProminent)

                Button {
                    manager.revealInFinder(path: item.path)
                } label: {
                    Label("定位", systemImage: "folder")
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.glass)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .glassEffect(
            .regular.tint(Color.white.opacity(0.03)).interactive(),
            in: .rect(cornerRadius: 10)
        )
    }
}
