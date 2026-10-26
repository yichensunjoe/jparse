import SwiftUI

public struct LightTaskCardView: View {
    public let task: TaskItem
    @ObservedObject var manager: BackendManager
    @State private var isHovered = false

    public init(task: TaskItem, manager: BackendManager) {
        self.task = task
        self.manager = manager
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header: Icon, File Name, Metadata, Badges
            HStack(alignment: .top, spacing: 12) {
                // Status Icon — Circle style
                ZStack {
                    Circle()
                        .fill(task.status.tintColor.opacity(0.10))
                        .frame(width: 36, height: 36)

                    Image(systemName: task.status.iconName)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(task.status.tintColor)
                }

                // File metadata
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text(task.filename)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(LightTheme.textPrimary)
                            .lineLimit(1)

                        if !task.relative_path.isEmpty && task.relative_path != task.filename {
                            Text("[\(task.relative_path)]")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(LightTheme.textMuted)
                                .lineLimit(1)
                        }
                    }

                    HStack(spacing: 6) {
                        Text(task.formattedSize)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(LightTheme.textSecondary)

                        Text("·")
                            .foregroundStyle(LightTheme.textMuted)

                        Text(task.created_at)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(LightTheme.textMuted)

                        if task.duration > 0 {
                            Text("·")
                                .foregroundStyle(LightTheme.textMuted)
                            Text(String(format: "%.1fs", task.duration))
                                .font(.system(size: 11, weight: .medium, design: .monospaced))
                                .foregroundStyle(LightTheme.accentBlue)
                        }
                    }
                }

                Spacer()

                // Badges
                HStack(spacing: 6) {
                    if task.doc_type != "unknown" {
                        Text(task.docTypeBadgeText)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(task.docTypeColor)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(task.docTypeColor.opacity(0.07), in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge))
                            .overlay(
                                RoundedRectangle(cornerRadius: LightTheme.radiusBadge)
                                    .stroke(task.docTypeColor.opacity(0.15), lineWidth: 1.0)
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
                    .background(task.status.tintColor.opacity(0.07), in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge))
                }
            }

            // Progress Bar (when active) — Capsule style
            if task.status == .probing || task.status == .processing || task.status == .queued {
                VStack(alignment: .leading, spacing: 5) {
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule()
                                .fill(LightTheme.controlBg)
                                .frame(height: 4)

                            Capsule()
                                .fill(
                                    LinearGradient(
                                        colors: [LightTheme.accentBlue, Color(red: 0.35, green: 0.60, blue: 1.0)],
                                        startPoint: .leading,
                                        endPoint: .trailing
                                    )
                                )
                                .frame(width: max(6, geo.size.width * CGFloat(task.progress) / 100.0), height: 4)
                                .animation(.spring(response: 0.35, dampingFraction: 0.8), value: task.progress)
                        }
                    }
                    .frame(height: 4)

                    HStack {
                        Text(task.status == .probing ? "探测版面拓扑与矢量特征中..." : "高清裁剪、神经翻译与出版排版中...")
                            .font(.system(size: 11))
                            .foregroundStyle(LightTheme.textSecondary)

                        Spacer()

                        Text("\(Int(task.progress))%")
                            .font(.system(size: 11, weight: .semibold, design: .monospaced))
                            .foregroundStyle(LightTheme.accentBlue)
                    }
                }
            }

            // Error display
            if let err = task.error, !err.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.octagon.fill")
                        .foregroundStyle(LightTheme.accentRed)
                    Text(err)
                        .font(.system(size: 11))
                        .foregroundStyle(LightTheme.accentRed)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(LightTheme.accentRed.opacity(0.06), in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge))
            }

            // Deliverables section (when completed)
            if task.status == .completed && !task.output_files.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("交付成果")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(LightTheme.textMuted)
                        .tracking(1)

                    VStack(spacing: 4) {
                        ForEach(task.output_files) { item in
                            deliverableRow(item: item)
                        }
                    }
                }
                .padding(.top, 2)
            }
        }
        .padding(14)
        .background(
            isHovered ? LightTheme.cardHover : LightTheme.cardBg,
            in: RoundedRectangle(cornerRadius: LightTheme.radiusCard)
        )
        .overlay(
            RoundedRectangle(cornerRadius: LightTheme.radiusCard)
                .stroke(isHovered ? LightTheme.borderHover : LightTheme.border, lineWidth: 1.0)
        )
        .shadow(
            color: isHovered ? Color.black.opacity(0.06) : LightTheme.shadowColor,
            radius: isHovered ? 6 : 3,
            y: 2
        )
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovered = hovering
            }
        }
    }

    @ViewBuilder
    private func deliverableRow(item: OutputFileItem) -> some View {
        HStack(spacing: 10) {
            Image(systemName: item.is_pdf ? "doc.richtext.fill" : "safari.fill")
                .font(.system(size: 13))
                .foregroundStyle(item.is_pdf ? LightTheme.accentRed.opacity(0.8) : LightTheme.accentBlue.opacity(0.8))

            Text(item.name)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(LightTheme.textPrimary)
                .lineLimit(1)

            if !item.formattedSize.isEmpty {
                Text(item.formattedSize)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(LightTheme.textMuted.opacity(0.7))
            }

            Spacer()

            // Ghost-style action buttons
            Button {
                manager.openFile(path: item.path)
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "eye")
                        .font(.system(size: 9))
                    Text("打开")
                        .font(.system(size: 11, weight: .medium))
                }
                .foregroundStyle(LightTheme.accentBlue)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(LightTheme.accentBlue.opacity(0.06), in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge))
            }
            .buttonStyle(.plain)

            Button {
                manager.revealInFinder(path: item.path)
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "folder")
                        .font(.system(size: 9))
                    Text("定位")
                        .font(.system(size: 11, weight: .medium))
                }
                .foregroundStyle(LightTheme.textSecondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(LightTheme.controlBg.opacity(0.6), in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(LightTheme.canvasBg.opacity(0.7), in: RoundedRectangle(cornerRadius: LightTheme.radiusButton))
    }
}
