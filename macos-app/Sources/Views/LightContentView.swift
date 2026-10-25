import SwiftUI

public struct LightContentView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        VStack(spacing: 0) {
            // 1. Raycast Top Header Bar
            LightHeaderView(manager: manager)

            // 2. Main Scrollable Workspace
            ScrollView(.vertical, showsIndicators: true) {
                VStack(alignment: .leading, spacing: 18) {
                    // Drop Zone
                    LightDropZoneView(manager: manager)

                    // Upload Progress Banner (if active)
                    if manager.isUploading {
                        HStack(spacing: 10) {
                            ProgressView()
                                .controlSize(.small)
                            Text(manager.uploadStatusMessage)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(LightTheme.accentBlue)
                            Spacer()
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(LightTheme.accentBlue.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(LightTheme.accentBlue.opacity(0.20), lineWidth: 1.0)
                        )
                    }

                    // Error Banner (if any)
                    if let err = manager.errorMessage {
                        HStack(spacing: 10) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(LightTheme.accentAmber)
                            Text(err)
                                .font(.system(size: 12))
                                .foregroundStyle(LightTheme.textPrimary)
                            Spacer()
                            Button {
                                manager.errorMessage = nil
                            } label: {
                                Image(systemName: "xmark")
                                    .font(.system(size: 10))
                                    .foregroundStyle(LightTheme.textMuted)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(LightTheme.accentAmber.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(LightTheme.accentAmber.opacity(0.25), lineWidth: 1.0)
                        )
                    }

                    // Section Bar: Title & Translation Engine Switcher
                    HStack(alignment: .center) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("文献流水线")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundStyle(LightTheme.textPrimary)

                            Text("(\(manager.tasks.count))")
                                .font(.system(size: 12, weight: .medium, design: .monospaced))
                                .foregroundStyle(LightTheme.textMuted)
                        }

                        Spacer()

                        // Translation Engine Switcher (Compact Raycast style)
                        HStack(spacing: 4) {
                            Text("翻译引擎:")
                                .font(.system(size: 11))
                                .foregroundStyle(LightTheme.textSecondary)

                            ForEach(TranslationService.allCases) { srv in
                                let isSelected = manager.selectedService == srv

                                Button {
                                    withAnimation(.spring(response: 0.25, dampingFraction: 0.75)) {
                                        manager.selectedService = srv
                                    }
                                } label: {
                                    Text(srv.shortTitle)
                                        .font(.system(size: 11, weight: isSelected ? .semibold : .regular))
                                        .foregroundStyle(isSelected ? LightTheme.accentBlue : LightTheme.textSecondary)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 3.5)
                                        .background(
                                            isSelected ? Color.white : Color.clear,
                                            in: RoundedRectangle(cornerRadius: 5)
                                        )
                                        .shadow(color: isSelected ? Color.black.opacity(0.06) : Color.clear, radius: 1, y: 1)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(3)
                        .background(LightTheme.controlBg, in: RoundedRectangle(cornerRadius: 7))
                    }
                    .padding(.top, 4)

                    // Task List or Empty Placeholder
                    if manager.tasks.isEmpty {
                        emptyStateView
                    } else {
                        LazyVStack(spacing: 12) {
                            ForEach(manager.tasks) { task in
                                LightTaskCardView(task: task, manager: manager)
                            }
                        }
                    }
                }
                .padding(22)
            }

            // 3. Bottom Footer
            LightFooterView(manager: manager)
        }
        .background(LightTheme.canvasBg)
    }

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(Color.white)
                    .frame(width: 56, height: 56)
                    .shadow(color: LightTheme.shadowColor, radius: 4, y: 2)

                Image(systemName: "tray")
                    .font(.system(size: 24))
                    .foregroundStyle(LightTheme.textMuted)
            }

            VStack(spacing: 4) {
                Text("当前转换队列为空")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(LightTheme.textPrimary)

                Text("拖入学术论文（MDPI/IEEE/Springer）或图书扫描件，即刻分流并生成高清成果")
                    .font(.system(size: 12))
                    .foregroundStyle(LightTheme.textSecondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 56)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(LightTheme.border, lineWidth: 1.0)
        )
    }
}
