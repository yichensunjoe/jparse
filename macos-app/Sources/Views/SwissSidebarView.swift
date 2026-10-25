import SwiftUI

public struct SwissSidebarView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header: Brand & Title
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Image(systemName: "magazine.fill")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(SwissTheme.accentCobalt)

                    Text("LITEPARSE STUDIO")
                        .font(.system(size: 13, weight: .bold, design: .monospaced))
                        .tracking(1.2)
                        .foregroundStyle(SwissTheme.textPrimary)
                }

                Text("双轨学术出版与文献重构工作台")
                    .font(.system(size: 11))
                    .foregroundStyle(SwissTheme.textSecondary)
            }
            .padding(.horizontal, 18)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider()
                .background(SwissTheme.hairline)

            // Scrollable Settings
            ScrollView(.vertical, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 20) {
                    // Section 1: Pipeline
                    VStack(alignment: .leading, spacing: 8) {
                        sectionHeader(title: "解析管线", subtitle: "PIPELINE MODE")

                        VStack(spacing: 4) {
                            ForEach(PipelineMode.allCases) { mode in
                                pipelineItem(for: mode)
                            }
                        }
                    }

                    // Section 2: Translation Service
                    VStack(alignment: .leading, spacing: 8) {
                        sectionHeader(title: "翻译引擎", subtitle: "TRANSLATION ENGINE")

                        VStack(spacing: 4) {
                            ForEach(TranslationService.allCases) { service in
                                serviceItem(for: service)
                            }
                        }
                    }

                    // Section 3: System Status & Security
                    VStack(alignment: .leading, spacing: 8) {
                        sectionHeader(title: "安全规范", subtitle: "SECURITY & ENGINE")

                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 6) {
                                Circle()
                                    .fill(manager.connectionStatus.indicatorColor)
                                    .frame(width: 6, height: 6)
                                Text(manager.connectionStatus.statusText)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(SwissTheme.textSecondary)
                            }

                            HStack(spacing: 6) {
                                Image(systemName: "lock.shield.fill")
                                    .font(.system(size: 11))
                                    .foregroundStyle(SwissTheme.accentEmerald)
                                Text("100% 本地离线处理 · 零云端留存")
                                    .font(.system(size: 10))
                                    .foregroundStyle(SwissTheme.textMuted)
                            }

                            HStack(spacing: 6) {
                                Image(systemName: "arrow.triangle.swap")
                                    .font(.system(size: 10))
                                    .foregroundStyle(SwissTheme.accentAmber)
                                Text("无碎词重叠 · 出版级三线表")
                                    .font(.system(size: 10))
                                    .foregroundStyle(SwissTheme.textMuted)
                            }
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(SwissTheme.surfaceBg.opacity(0.4), in: RoundedRectangle(cornerRadius: 6))
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(SwissTheme.hairline, lineWidth: 1.0)
                        )
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 16)
            }

            Divider()
                .background(SwissTheme.hairline)

            // Bottom Actions
            VStack(spacing: 8) {
                Button {
                    manager.revealOutbox()
                } label: {
                    HStack {
                        Image(systemName: "folder.fill")
                            .font(.system(size: 11))
                        Text("打开成果目录 (outbox/)")
                            .font(.system(size: 11, weight: .medium))
                        Spacer()
                        Image(systemName: "arrow.up.right")
                            .font(.system(size: 9))
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.plain)
                .swissButton(isProminent: true)

                HStack(spacing: 8) {
                    Button {
                        manager.revealInbox()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "tray.and.arrow.down")
                                .font(.system(size: 10))
                            Text("投递箱")
                                .font(.system(size: 11))
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.plain)
                    .swissButton()

                    Button {
                        manager.clearCompleted()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "trash")
                                .font(.system(size: 10))
                            Text("清空完成")
                                .font(.system(size: 11))
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.plain)
                    .swissButton()
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 14)
        }
        .frame(width: 270)
        .background(SwissTheme.sidebarBg)
        .overlay(
            Rectangle()
                .frame(width: 1)
                .foregroundStyle(SwissTheme.hairline),
            alignment: .trailing
        )
    }

    private func sectionHeader(title: String, subtitle: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(title)
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(SwissTheme.textPrimary)

            Text(subtitle)
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .foregroundStyle(SwissTheme.textMuted)

            Spacer()
        }
        .padding(.horizontal, 4)
    }

    @ViewBuilder
    private func pipelineItem(for mode: PipelineMode) -> some View {
        let isSelected = manager.selectedPipeline == mode

        Button {
            withAnimation(.spring(response: 0.25, dampingFraction: 0.75)) {
                manager.selectedPipeline = mode
            }
        } label: {
            HStack(spacing: 10) {
                // Indicator strip
                Rectangle()
                    .fill(isSelected ? SwissTheme.accentCobalt : Color.clear)
                    .frame(width: 3, height: 26)
                    .cornerRadius(1.5)

                VStack(alignment: .leading, spacing: 2) {
                    Text(mode.title)
                        .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                        .foregroundStyle(isSelected ? SwissTheme.textPrimary : SwissTheme.textSecondary)

                    Text(mode.subtitle)
                        .font(.system(size: 10))
                        .foregroundStyle(SwissTheme.textMuted)
                        .lineLimit(1)
                }

                Spacer()
            }
            .padding(.vertical, 6)
            .padding(.trailing, 8)
            .background(
                isSelected ? SwissTheme.surfaceBg : Color.clear,
                in: RoundedRectangle(cornerRadius: 6)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? SwissTheme.accentCobalt.opacity(0.3) : Color.clear, lineWidth: 1.0)
            )
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func serviceItem(for service: TranslationService) -> some View {
        let isSelected = manager.selectedService == service

        Button {
            withAnimation(.spring(response: 0.25, dampingFraction: 0.75)) {
                manager.selectedService = service
            }
        } label: {
            HStack(spacing: 10) {
                Rectangle()
                    .fill(isSelected ? SwissTheme.accentAmber : Color.clear)
                    .frame(width: 3, height: 26)
                    .cornerRadius(1.5)

                VStack(alignment: .leading, spacing: 2) {
                    Text(service.title)
                        .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                        .foregroundStyle(isSelected ? SwissTheme.textPrimary : SwissTheme.textSecondary)

                    Text(service.subtitle)
                        .font(.system(size: 10))
                        .foregroundStyle(SwissTheme.textMuted)
                        .lineLimit(1)
                }

                Spacer()
            }
            .padding(.vertical, 6)
            .padding(.trailing, 8)
            .background(
                isSelected ? SwissTheme.surfaceBg : Color.clear,
                in: RoundedRectangle(cornerRadius: 6)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? SwissTheme.accentAmber.opacity(0.3) : Color.clear, lineWidth: 1.0)
            )
        }
        .buttonStyle(.plain)
    }
}
