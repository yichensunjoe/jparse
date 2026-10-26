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
                VStack(alignment: .leading, spacing: 16) {
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
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(LightTheme.accentBlue.opacity(0.06), in: RoundedRectangle(cornerRadius: LightTheme.radiusButton))
                        .overlay(
                            RoundedRectangle(cornerRadius: LightTheme.radiusButton)
                                .stroke(LightTheme.accentBlue.opacity(0.15), lineWidth: 1.0)
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
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(LightTheme.accentAmber.opacity(0.08), in: RoundedRectangle(cornerRadius: LightTheme.radiusButton))
                        .overlay(
                            RoundedRectangle(cornerRadius: LightTheme.radiusButton)
                                .stroke(LightTheme.accentAmber.opacity(0.20), lineWidth: 1.0)
                        )
                    }

                    // Section Bar: Title & Translation Engine Switcher
                    HStack(alignment: .center) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("文献流水线")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(LightTheme.textPrimary)

                            Text("\(manager.tasks.count)")
                                .font(.system(size: 11, weight: .medium, design: .monospaced))
                                .foregroundStyle(LightTheme.textMuted)
                        }

                        Spacer()

                        // Translation Engine Switcher
                        HStack(spacing: 4) {
                            Text("翻译:")
                                .font(.system(size: 11))
                                .foregroundStyle(LightTheme.textMuted)

                            ForEach(TranslationService.allCases) { srv in
                                let isSelected = manager.selectedService == srv

                                Button {
                                    withAnimation(.spring(response: 0.25, dampingFraction: 0.75)) {
                                        manager.selectedService = srv
                                    }
                                } label: {
                                    Text(srv.shortTitle)
                                        .font(.system(size: 11, weight: isSelected ? .medium : .regular))
                                        .foregroundStyle(isSelected ? LightTheme.accentBlue : LightTheme.textSecondary)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 3)
                                        .background(
                                            isSelected ? Color.white : Color.clear,
                                            in: RoundedRectangle(cornerRadius: 5)
                                        )
                                        .shadow(color: isSelected ? Color.black.opacity(0.05) : Color.clear, radius: 1, y: 1)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(3)
                        .background(LightTheme.controlBg, in: RoundedRectangle(cornerRadius: LightTheme.radiusButton))
                    }
                    .padding(.top, 2)

                    // Task List or Empty Placeholder
                    if manager.tasks.isEmpty {
                        emptyStateView
                    } else {
                        LazyVStack(spacing: 10) {
                            ForEach(manager.tasks) { task in
                                LightTaskCardView(task: task, manager: manager)
                            }
                        }
                    }
                }
                .padding(20)
            }

            // 3. Bottom Footer
            LightFooterView(manager: manager)
        }
        .background(LightTheme.canvasBg)
    }

    private var emptyStateView: some View {
        VStack(spacing: 14) {
            // Stacked documents illustration
            ZStack {
                // Back doc — rotated
                RoundedRectangle(cornerRadius: 6)
                    .fill(LightTheme.controlBg.opacity(0.6))
                    .frame(width: 34, height: 42)
                    .rotationEffect(.degrees(-8))
                    .offset(x: -6, y: 3)

                // Mid doc
                RoundedRectangle(cornerRadius: 6)
                    .fill(LightTheme.controlBg.opacity(0.8))
                    .frame(width: 34, height: 42)
                    .rotationEffect(.degrees(4))
                    .offset(x: 4, y: 1)

                // Front doc
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.white)
                    .frame(width: 34, height: 42)
                    .shadow(color: LightTheme.shadowColor, radius: 3, y: 2)
                    .overlay(
                        VStack(spacing: 3) {
                            RoundedRectangle(cornerRadius: 1)
                                .fill(LightTheme.accentBlue.opacity(0.25))
                                .frame(width: 18, height: 2)
                            RoundedRectangle(cornerRadius: 1)
                                .fill(LightTheme.controlBg)
                                .frame(width: 22, height: 2)
                            RoundedRectangle(cornerRadius: 1)
                                .fill(LightTheme.controlBg)
                                .frame(width: 16, height: 2)
                        }
                    )
            }
            .frame(width: 60, height: 52)

            VStack(spacing: 4) {
                Text("拖入文献，即刻重构")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(LightTheme.textPrimary)

                Text("支持 MDPI · IEEE · Springer 矢量论文与历史扫描专著")
                    .font(.system(size: 12))
                    .foregroundStyle(LightTheme.textSecondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 48)
        .background(LightTheme.cardBg, in: RoundedRectangle(cornerRadius: LightTheme.radiusCard))
        .overlay(
            RoundedRectangle(cornerRadius: LightTheme.radiusCard)
                .stroke(LightTheme.border, style: StrokeStyle(lineWidth: 1.0, dash: [6, 4]))
        )
    }
}
