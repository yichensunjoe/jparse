import SwiftUI

public struct SwissTaskRowView: View {
    public let task: TaskItem
    @ObservedObject var manager: BackendManager
    @State private var isHovered = false

    public init(task: TaskItem, manager: BackendManager) {
        self.task = task
        self.manager = manager
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Main Line: Icon, Title, Path, Badges, Status
            HStack(alignment: .center, spacing: 12) {
                // Technical format marker
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(task.status.tintColor.opacity(0.15))
                        .frame(width: 32, height: 32)

                    Image(systemName: task.status.iconName)
                        .font(.system(size: 14))
                        .foregroundStyle(task.status.tintColor)
                }

                // File Name & Path
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text(task.filename)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(SwissTheme.textPrimary)
                            .lineLimit(1)

                        if !task.relative_path.isEmpty && task.relative_path != task.filename {
                            Text("[\(task.relative_path)]")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(SwissTheme.textMuted)
                                .lineLimit(1)
                        }
                    }

                    HStack(spacing: 8) {
                        Text(task.formattedSize)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(SwissTheme.textSecondary)

                        Text("·")
                            .foregroundStyle(SwissTheme.textMuted)

                        Text(task.created_at)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(SwissTheme.textMuted)

                        if task.duration > 0 {
                            Text("·")
                                .foregroundStyle(SwissTheme.textMuted)
                            Text(String(format: "%.1fs", task.duration))
                                .font(.system(size: 10, weight: .medium, design: .monospaced))
                                .foregroundStyle(SwissTheme.accentCobalt)
                        }
                    }
                }

                Spacer()

                // Swiss Badges
                HStack(spacing: 8) {
                    if task.doc_type != "unknown" {
                        Text(task.docTypeBadgeText)
                            .font(.system(size: 10, weight: .medium, design: .monospaced))
                            .foregroundStyle(task.docTypeColor)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 3)
                            .background(task.docTypeColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(task.docTypeColor.opacity(0.35), lineWidth: 1.0)
                            )
                    }

                    HStack(spacing: 4) {
                        Circle()
                            .fill(task.status.tintColor)
                            .frame(width: 5, height: 5)
                        Text(task.status.localizedDescription)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(task.status.tintColor)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(task.status.tintColor.opacity(0.10), in: RoundedRectangle(cornerRadius: 4))
                }
            }

            // Progress Bar (if running)
            if task.status == .probing || task.status == .processing || task.status == .queued {
                VStack(alignment: .leading, spacing: 4) {
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Rectangle()
                                .fill(Color.white.opacity(0.06))
                                .frame(height: 2)

                            Rectangle()
                                .fill(SwissTheme.accentCobalt)
                                .frame(width: max(4, geo.size.width * CGFloat(task.progress) / 100.0), height: 2)
                                .animation(.linear(duration: 0.2), value: task.progress)
                        }
                    }
                    .frame(height: 2)

                    HStack {
                        Text(task.status == .probing ? "探测版面拓扑与特征中..." : "进行高清图表裁剪、神经翻译与出版排版中...")
                            .font(.system(size: 10))
                            .foregroundStyle(SwissTheme.textSecondary)

                        Spacer()

                        Text("\(Int(task.progress))%")
                            .font(.system(size: 10, weight: .medium, design: .monospaced))
                            .foregroundStyle(SwissTheme.accentCobalt)
                    }
                }
            }

            // Error display
            if let err = task.error, !err.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "xmark.octagon.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(SwissTheme.accentCrimson)
                    Text(err)
                        .font(.system(size: 11))
                        .foregroundStyle(SwissTheme.accentCrimson)
                }
                .padding(8)
                .background(SwissTheme.accentCrimson.opacity(0.08), in: RoundedRectangle(cornerRadius: 4))
            }

            // Deliverables Section
            if task.status == .completed && !task.output_files.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("交付产物 / DELIVERABLES")
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundStyle(SwissTheme.textMuted)

                    VStack(spacing: 4) {
                        ForEach(task.output_files) { item in
                            deliverableItem(item: item)
                        }
                    }
                }
                .padding(.top, 2)
            }
        }
        .padding(14)
        .background(
            isHovered ? SwissTheme.surfaceBg : SwissTheme.surfaceBg.opacity(0.50),
            in: RoundedRectangle(cornerRadius: 6)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(isHovered ? SwissTheme.hairlineStrong : SwissTheme.hairline, lineWidth: 1.0)
        )
        .onHover { hovering in
            isHovered = hovering
        }
    }

    @ViewBuilder
    private func deliverableItem(item: OutputFileItem) -> some View {
        HStack(spacing: 8) {
            Image(systemName: item.is_pdf ? "doc.richtext" : "safari")
                .font(.system(size: 12))
                .foregroundStyle(item.is_pdf ? SwissTheme.accentCobalt : SwissTheme.accentAmber)

            Text(item.name)
                .font(.system(size: 11, weight: .medium, design: .monospaced))
                .foregroundStyle(SwissTheme.textPrimary)
                .lineLimit(1)

            if !item.formattedSize.isEmpty {
                Text("(\(item.formattedSize))")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(SwissTheme.textMuted)
            }

            Spacer()

            Button {
                manager.openFile(path: item.path)
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "eye.fill")
                        .font(.system(size: 9))
                    Text("打开")
                }
            }
            .buttonStyle(.plain)
            .swissButton(isProminent: true)

            Button {
                manager.revealInFinder(path: item.path)
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "folder")
                        .font(.system(size: 9))
                    Text("定位")
                }
            }
            .buttonStyle(.plain)
            .swissButton()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(SwissTheme.canvasBg.opacity(0.6), in: RoundedRectangle(cornerRadius: 4))
    }
}
