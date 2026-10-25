import SwiftUI

public struct GlassControlBarView: View {
    @ObservedObject var manager: BackendManager

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        GlassEffectContainer(spacing: 16) {
            VStack(spacing: 14) {
                // Row 1: Pipeline Selector
                HStack(spacing: 12) {
                    Label("解析管线", systemImage: "point.3.filled.connected.trianglepath.dotted")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Color(white: 0.85))
                        .frame(width: 86, alignment: .leading)

                    HStack(spacing: 8) {
                        ForEach(PipelineMode.allCases) { mode in
                            pipelineButton(for: mode)
                        }
                    }

                    Spacer()
                }

                Divider()
                    .background(Color.white.opacity(0.10))

                // Row 2: Translation Service Selector
                HStack(spacing: 12) {
                    Label("翻译引擎", systemImage: "character.bubble.fill")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Color(white: 0.85))
                        .frame(width: 86, alignment: .leading)

                    HStack(spacing: 8) {
                        ForEach(TranslationService.allCases) { service in
                            serviceButton(for: service)
                        }
                    }

                    Spacer()

                    // Quick help or info badge
                    Text(manager.selectedPipeline.subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(Color(white: 0.55))
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity)
            // Liquid Glass card wrapper for control bar
            .glassEffect(
                .regular.tint(Color.indigo.opacity(0.10)).interactive(),
                in: .rect(cornerRadius: 18)
            )
        }
    }

    @ViewBuilder
    private func pipelineButton(for mode: PipelineMode) -> some View {
        let isSelected = manager.selectedPipeline == mode

        Button {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                manager.selectedPipeline = mode
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: mode.iconName)
                    .font(.system(size: 11, weight: .medium))
                Text(mode.shortTitle)
                    .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
            }
            .foregroundStyle(isSelected ? Color.white : Color(white: 0.72))
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .glassEffect(
                isSelected
                    ? .regular.tint(Color.blue.opacity(0.35)).interactive()
                    : .regular.tint(Color.white.opacity(0.04)).interactive(),
                in: .capsule
            )
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func serviceButton(for service: TranslationService) -> some View {
        let isSelected = manager.selectedService == service

        Button {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                manager.selectedService = service
            }
        } label: {
            Text(service.shortTitle)
                .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                .foregroundStyle(isSelected ? Color.white : Color(white: 0.72))
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .glassEffect(
                    isSelected
                        ? .regular.tint(Color.purple.opacity(0.30)).interactive()
                        : .regular.tint(Color.white.opacity(0.04)).interactive(),
                    in: .capsule
                )
        }
        .buttonStyle(.plain)
    }
}
