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
                // Status Icon
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(task.status.tintColor.opacity(0.12))
                        .frame(width: 36, height: 36)

                    Image(systemName: task.status.iconName)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(task.status.tintColor)
                }

                // File metadata
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text(task.filename)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(LightTheme.textPrimary)
                            .lineLimit(1)

                        if !task.relative_path.isEmpty && task.relative_path != task.filename {
                            Text("[\(task.relative_path)]")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(LightTheme.textMuted)
                                .lineLimit(1)
                        }
                    }

                    HStack(spacing: 8) {
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
                            Text(String(format: "耗时 %.1fs", task.duration))
                                .font(.system(size: 11, weight: .medium, design: .monospaced))
                                .foregroundStyle(LightTheme.accentBlue)
                        }
                    }
                }

                Spacer()

                // Badges
                HStack(spacing: 8) {
                    if task.doc_type != "unknown" {
                        Text(task.docTypeBadgeText)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(task.docTypeColor)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(task.docTypeColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(task.docTypeColor.opacity(0.20), lineWidth: 1.0)
                            )
                    }

                    HStack(spacing: 5) {
                        Circle()
                            .fill(task.status.tintColor)
                            .frame(width: 6, height: 6)
                        Text(task.status.localizedDescription)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(task.status.tintColor)
                    }
                    .padding(.horizontal, 9)
                    .padding(.vertical, 4)
                    .background(task.status.tintColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
                }
            }

            // Progress Bar (when active)
            if task.status == .probing || task.status == .processing || task.status == .queued {
                VStack(alignment: .leading, spacing: 5) {
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(LightTheme.controlBg)
                                .frame(height: 4)

                            RoundedRectangle(cornerRadius: 2)
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
                        Text(task.status == .probing ? "探测版面拓扑与矢量特征中..." : "进行高清图表裁剪、神经翻译与出版排版中...")
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
                .background(LightTheme.accentRed.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
            }

            // Deliverables section (when completed)
            if task.status == .completed && !task.output_files.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("交付产物 / DELIVERABLES")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(LightTheme.textMuted)

                    VStack(spacing: 6) {
                        ForEach(task.output_files) { item in
                            deliverableRow(item: item)
                        }
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding(16)
        .background(
            isHovered ? LightTheme.cardHover : LightTheme.cardBg,
            in: RoundedRectangle(cornerRadius: 12)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isHovered ? LightTheme.borderHover : LightTheme.border, lineWidth: 1.0)
        )
        .shadow(
            color: isHovered ? Color.black.opacity(0.06) : LightTheme.shadowColor,
            radius: isHovered ? 6 : 4,
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
                .font(.system(size: 14))
                .foregroundStyle(item.is_pdf ? LightTheme.accentRed : LightTheme.accentBlue)

            Text(item.name)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(LightTheme.textPrimary)
                .lineLimit(1)

            if !item.formattedSize.isEmpty {
                Text("(\(item.formattedSize))")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(LightTheme.textMuted)
            }

            Spacer()

            Button {
                manager.openFile(path: item.path)
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "eye.fill")
                        .font(.system(size: 9))
                    Text("打开")
                }
            }
            .buttonStyle(.plain)
            .lightButton(isProminent: true)

            Button {
                manager.revealInFinder(path: item.path)
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "folder")
                        .font(.system(size: 9))
                    Text("定位")
                }
            }
            .buttonStyle(.plain)
            .lightButton()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(LightTheme.canvasBg, in: RoundedRectangle(cornerRadius: 8))
    }
}
