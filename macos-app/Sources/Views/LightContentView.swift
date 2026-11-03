import SwiftUI

public struct LightContentView: View {
    @ObservedObject var manager: BackendManager
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isWindowTargeted = false

    public init(manager: BackendManager) {
        self.manager = manager
    }

    public var body: some View {
        VStack(spacing: 0) {
            LightHeaderView(manager: manager)

            if manager.isUploading || manager.errorMessage != nil {
                VStack(spacing: 8) {
                    if manager.isUploading { uploadBanner }
                    if let error = manager.errorMessage { errorBanner(error) }
                }
                .frame(maxWidth: 940)
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 24)
                .padding(.top, 14)
            }

            if manager.tasks.isEmpty {
                emptyStage
                    .transition(.opacity)
            } else {
                taskScroll
                    .transition(.opacity)
            }

            LightFooterView(manager: manager)
        }
        .background { canvasBackground }
        .ignoresSafeArea(.container, edges: .top)
        .overlay { windowDropOverlay }
        .animation(reduceMotion ? nil : .smooth(duration: 0.30), value: manager.tasks.isEmpty)
        // 整个窗口都是投递区：拖到标题、卡片或空白处也能收下文件。
        .dropDestination(for: URL.self) { urls, _ in
            manager.handleDroppedURLs(urls)
            return true
        } isTargeted: { targeted in
            withAnimation(.smooth(duration: 0.20)) { isWindowTargeted = targeted }
        }
    }

    // MARK: - Background

    private var canvasBackground: some View {
        ZStack {
            // 暖纸渐变 + 两团大半径低透明度氛围光，负责“纸张感”而不是“花”。
            LightTheme.canvasGradient

            RadialGradient(
                colors: [LightTheme.accentBlue.opacity(0.045), Color.clear],
                center: .topLeading,
                startRadius: 0,
                endRadius: 560
            )

            RadialGradient(
                colors: [LightTheme.accentCyan.opacity(0.030), Color.clear],
                center: .bottomTrailing,
                startRadius: 0,
                endRadius: 660
            )

            RadialGradient(
                colors: [Color.white.opacity(0.85), Color.clear],
                center: .top,
                startRadius: 0,
                endRadius: 520
            )
            .offset(y: -160)
        }
        .ignoresSafeArea()
    }

    // MARK: - Empty Stage（无任务：居中 Hero）

    private var emptyStage: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 16)

            LightDropZoneView(manager: manager, isHero: true)
                .frame(maxWidth: 780)

            Spacer(minLength: 16)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, 40)
        .padding(.vertical, 20)
    }

    // MARK: - Task Scroll

    private var taskScroll: some View {
        ScrollView(.vertical, showsIndicators: true) {
            VStack(alignment: .leading, spacing: 16) {
                LightDropZoneView(manager: manager)
                    .frame(maxWidth: 940)
                    .frame(maxWidth: .infinity)

                sectionBar
                    .frame(maxWidth: 940)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 2)

                // 用非惰性 VStack：任务上限 200，惰性堆栈会在每秒轮询时
                // 重算可见区，配合动画会让滚动条抽动。
                VStack(spacing: 12) {
                    ForEach(manager.tasks) { task in
                        LightTaskCardView(task: task, manager: manager)
                            .transition(reduceMotion ? .opacity : .asymmetric(
                                insertion: .scale(scale: 0.98)
                                    .combined(with: .opacity)
                                    .combined(with: .move(edge: .top)),
                                removal: .scale(scale: 0.98).combined(with: .opacity)
                            ))
                    }
                }
                .frame(maxWidth: 940)
                .frame(maxWidth: .infinity)
                // 动画只跟随“任务集合本身”变化，不挂到 ScrollView 上：
                // 否则滚动容器的偏移与滚动条也会被弹簧动画带动。
                .animation(
                    reduceMotion ? nil : .spring(response: 0.46, dampingFraction: 0.86),
                    value: manager.tasks.map(\.id)
                )
            }
            .padding(.horizontal, 24)
            .padding(.top, 18)
            .padding(.bottom, 24)
        }
        .animation(.smooth(duration: 0.28), value: manager.isUploading)
    }

    @ViewBuilder
    private var windowDropOverlay: some View {
        if isWindowTargeted {
            ZStack {
                LightTheme.accentBlue.opacity(0.035)

                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(LightTheme.accentBlue.opacity(0.55), lineWidth: 2)
                    .padding(10)

                VStack(spacing: 7) {
                    Image(systemName: "arrow.down.doc.fill")
                        .font(.system(size: 24, weight: .medium))
                        .foregroundStyle(LightTheme.accentBlue)

                    Text("松开即可投递")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(LightTheme.textPrimary)
                }
                .padding(.horizontal, 24)
                .padding(.vertical, 16)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Color.white.opacity(0.55), lineWidth: 1)
                )
                .shadow(color: Color.black.opacity(0.12), radius: 20, y: 8)
            }
            .allowsHitTesting(false)
            .transition(.opacity)
        }
    }

    // MARK: - Banners

    private var uploadBanner: some View {
        HStack(spacing: 10) {
            ProgressView()
                .controlSize(.small)
                .tint(LightTheme.accentBlue)

            Text(manager.uploadStatusMessage)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(LightTheme.textPrimary)

            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(LightTheme.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(LightTheme.border, lineWidth: 1)
        )
    }

    private func errorBanner(_ err: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.circle.fill")
                .font(.system(size: 13))
                .foregroundStyle(LightTheme.accentRed)

            Text(err)
                .font(.system(size: 12))
                .foregroundStyle(LightTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)

            Spacer(minLength: 8)

            Button {
                withAnimation(.smooth(duration: 0.22)) {
                    manager.errorMessage = nil
                }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(LightTheme.textMuted)
                    .frame(width: 18, height: 18)
                    .background(Color.black.opacity(0.05), in: Circle())
            }
            .buttonStyle(PressableButtonStyle(pressedScale: 0.9))
            .help("关闭提示")
            .accessibilityLabel("关闭提示")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(LightTheme.accentRed.opacity(0.06), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(LightTheme.accentRed.opacity(0.16), lineWidth: 1)
        )
    }

    // MARK: - Section Bar

    private var sectionBar: some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Text("最近任务")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(LightTheme.textPrimary)

            Text("\(manager.tasks.count)")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(LightTheme.textMuted)
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
