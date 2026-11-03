import SwiftUI

public struct LightTaskCardView: View {
    public let task: TaskItem
    @ObservedObject var manager: BackendManager
    @State private var isHovered = false

    public init(task: TaskItem, manager: BackendManager) {
        self.task = task
        self.manager = manager
    }

    /// 只为探测或处理中显示阶段状态；排队任务不显示虚构进度。
    private var isActive: Bool {
        task.status == .probing || task.status == .processing
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 13) {
            header

            if isActive {
                progressSection
            }

            if let err = task.error, !err.isEmpty {
                errorBox(err)
            }

            if task.status == .completed && !task.output_files.isEmpty {
                deliverables
            }
        }
        .padding(16)
        .background {
            ZStack {
                RoundedRectangle(cornerRadius: LightTheme.radiusCard, style: .continuous)
                    .fill(isHovered ? LightTheme.cardHover : LightTheme.cardBg)

                // 悬浮时透出 4% 的状态色，只做环境反射，不抢内容。
                if isHovered {
                    RoundedRectangle(cornerRadius: LightTheme.radiusCard, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [task.status.tintColor.opacity(0.05), Color.clear],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                }
            }
        }
        .overlay(
            RoundedRectangle(cornerRadius: LightTheme.radiusCard, style: .continuous)
                .strokeBorder(
                    isHovered ? LightTheme.borderHover : LightTheme.border,
                    lineWidth: 1
                )
        )
        .shadow(
            color: LightTheme.shadowColor,
            radius: isHovered ? 14 : 8,
            y: isHovered ? 5 : 2
        )
        .onHover { hovering in
            withAnimation(.smooth(duration: 0.24)) {
                isHovered = hovering
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            statusGlyph

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 7) {
                    Text(task.filename)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(LightTheme.textPrimary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .layoutPriority(1)
                        .help(task.filename)
                        .textSelection(.enabled)

                    if !task.relative_path.isEmpty && task.relative_path != task.filename {
                        Text(task.relative_path)
                            .font(.system(size: 11))
                            .foregroundStyle(LightTheme.textMuted)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }

                HStack(spacing: 6) {
                    Text(task.formattedSize)
                        .monospacedDigit()

                    Text("·").foregroundStyle(LightTheme.textMuted)

                    Text(task.created_at)
                        .monospacedDigit()

                    if task.duration > 0 {
                        Text("·").foregroundStyle(LightTheme.textMuted)
                        Text(String(format: "%.1fs", task.duration))
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(LightTheme.textSecondary)
                            .monospacedDigit()
                            .contentTransition(.numericText())
                    }
                }
                .font(.system(size: 11))
                .foregroundStyle(LightTheme.textSecondary)
            }

            Spacer(minLength: 8)

            HStack(spacing: 6) {
                if task.doc_type != "unknown" {
                    Text(task.docTypeBadgeText)
                        .font(.system(size: 10.5, weight: .medium))
                        .foregroundStyle(LightTheme.textSecondary)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3.5)
                        .background(
                            Color.black.opacity(0.045),
                            in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge, style: .continuous)
                        )
                }

                statusPill
            }
        }
    }

    private var statusGlyph: some View {
        RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(task.status.tintColor.opacity(0.10))
            .frame(width: 30, height: 30)
            .overlay(
                Image(systemName: task.status.iconName)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(task.status.tintColor)
                    .contentTransition(.symbolEffect(.replace))
            )
    }

    private var statusPill: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(task.status.tintColor)
                .frame(width: 5, height: 5)

            Text(task.status.localizedDescription)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(task.status.tintColor)
                .lineLimit(1)
                .fixedSize()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3.5)
        .background(
            task.status.tintColor.opacity(0.08),
            in: RoundedRectangle(cornerRadius: LightTheme.radiusBadge, style: .continuous)
        )
    }

    // MARK: - Progress

    private var progressSection: some View {
        HStack(spacing: 8) {
            ProgressView()
                .controlSize(.small)
                .tint(task.status.tintColor)

            Text(task.status == .probing ? "正在识别文档类型和版面…" : "处理时间取决于文档大小和版面。")
                .font(.system(size: 12))
                .foregroundStyle(LightTheme.textSecondary)
        }
        .accessibilityElement(children: .combine)
    }

    // MARK: - Error

    private func errorBox(_ err: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.circle.fill")
                .font(.system(size: 12))
                .foregroundStyle(LightTheme.accentRed)

            Text(err)
                .font(.system(size: 11.5))
                .foregroundStyle(LightTheme.accentRed)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)

            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LightTheme.accentRed.opacity(0.055),
            in: RoundedRectangle(cornerRadius: 9, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(LightTheme.accentRed.opacity(0.14), lineWidth: 1)
        )
    }

    // MARK: - Deliverables

    private var deliverables: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("交付成果")
                .font(.system(size: 10.5, weight: .semibold))
                .tracking(0.4)
                .foregroundStyle(LightTheme.textMuted)

            VStack(spacing: 0) {
                ForEach(Array(task.output_files.enumerated()), id: \.element.id) { index, item in
                    DeliverableRow(item: item, manager: manager)

                    if index < task.output_files.count - 1 {
                        Rectangle()
                            .fill(LightTheme.hairline)
                            .frame(height: 1)
                            .padding(.leading, 40)
                    }
                }
            }
            .background(
                LightTheme.canvas.opacity(0.65),
                in: RoundedRectangle(cornerRadius: 10, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(LightTheme.hairline, lineWidth: 1)
            )
        }
    }
}

// MARK: - Deliverable Row

private struct DeliverableRow: View {
    let item: OutputFileItem
    @ObservedObject var manager: BackendManager
    @State private var isHovered = false

    private var tint: Color {
        item.is_pdf ? LightTheme.accentBlue : LightTheme.accentCyan
    }

    var body: some View {
        HStack(spacing: 10) {
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(tint.opacity(0.10))
                .frame(width: 22, height: 22)
                .overlay(
                    Image(systemName: item.is_pdf ? "doc.richtext.fill" : "safari.fill")
                        .font(.system(size: 10.5, weight: .medium))
                        .foregroundStyle(tint)
                )

            Text(item.name)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(LightTheme.textPrimary)
                .lineLimit(1)
                .truncationMode(.middle)
                .help(item.name)
                .layoutPriority(1)

            if !item.formattedSize.isEmpty {
                Text(item.formattedSize)
                    .font(.system(size: 10.5))
                    .foregroundStyle(LightTheme.textMuted)
                    .monospacedDigit()
            }

            Spacer(minLength: 8)

            Button {
                manager.openFile(path: item.path)
            } label: {
                Text("打开")
                    .font(.system(size: 11.5, weight: .medium))
                    .foregroundStyle(LightTheme.accentBlue)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3.5)
                    .modifier(RowHoverModifier(tint: LightTheme.accentBlue.opacity(0.10)))
            }
            .buttonStyle(PressableButtonStyle(pressedScale: 0.94))
            .help("用默认应用打开（PDF 优先用预览）")
            .accessibilityLabel("打开 \(item.name)")

            Button {
                manager.revealInFinder(path: item.path)
            } label: {
                Image(systemName: "folder")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(LightTheme.textSecondary)
                    .frame(width: 22, height: 22)
                    .modifier(RowHoverModifier(tint: Color.black.opacity(0.06)))
            }
            .buttonStyle(PressableButtonStyle(pressedScale: 0.94))
            .help("在访达中定位此文件")
            .accessibilityLabel("在访达中定位 \(item.name)")
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .background(
            isHovered ? Color.black.opacity(0.025) : Color.clear
        )
        .onHover { hovering in
            withAnimation(.smooth(duration: 0.16)) { isHovered = hovering }
        }
    }
}

/// 行内按钮悬停底色（ViewModifier 的 @State 在视图树里稳定生效）。
private struct RowHoverModifier: ViewModifier {
    let tint: Color
    @State private var hovered = false

    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(hovered ? tint : Color.clear)
            )
            .contentShape(Rectangle())
            .onHover { hovering in
                withAnimation(.smooth(duration: 0.16)) { hovered = hovering }
            }
    }
}
