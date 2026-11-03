import SwiftUI

/// 精密学术工作台的浅色设计系统：
/// - 画布是极浅的暖纸色，内容卡保持纯白，让文档始终是视觉中心；
/// - 品牌色收深为墨蓝（#1F5F8A），像校样上的批注，而不是系统高亮；
/// - 状态色降低荧光感，卡片仍靠留白、字号和发丝线建立层级。
public enum LightTheme {
    private static var settings: AppSettings { AppSettings.shared }

    // MARK: - Canvas
    public static var canvas: Color { settings.canvasTone.palette.canvas }
    public static var canvasTop: Color { settings.canvasTone.palette.top }
    public static var canvasBottom: Color { settings.canvasTone.palette.bottom }
    public static var canvasBg: Color { canvas }
    public static let cardBg = Color.white
    public static var cardHover: Color { settings.canvasTone.palette.cardHover }
    public static var controlBg: Color { settings.canvasTone.palette.control }
    public static var controlDeep: Color { settings.canvasTone.palette.controlDeep }
    public static var pillActiveBg: Color { accentBlue.opacity(0.18) } // 选中态：冷调纸片，压在暖轨上
    public static var hairline: Color { textPrimary.opacity(0.10) }

    // MARK: - Accent（墨蓝为主，状态色收深，文本保持 ≥4.5:1）
    public static var accentBlue: Color { settings.accent.palette.base }
    public static var accentBlueHover: Color { settings.accent.palette.hover }
    public static var accentBluePressed: Color { settings.accent.palette.pressed }
    public static let accentIndigo = Color(red: 0.290, green: 0.365, blue: 0.510)  // #4A5D82
    public static let accentViolet = Color(red: 0.486, green: 0.353, blue: 0.400)  // #7C5A66
    public static var accentCyan: Color { settings.accent.palette.secondary }
    // 状态色不随主题切换：探测/处理必须始终能和品牌主色区分。
    public static let statusProbing = Color(red: 0.122, green: 0.373, blue: 0.541) // #1F5F8A
    public static let statusProcessing = Color(red: 0.165, green: 0.451, blue: 0.478) // #2A737A
    public static let accentGreen = Color(red: 0.239, green: 0.478, blue: 0.345)   // #3D7A58
    public static let accentAmber = Color(red: 0.584, green: 0.373, blue: 0.157)   // #955F28
    public static let accentRed = Color(red: 0.690, green: 0.267, blue: 0.290)     // #B0444A

    // MARK: - Gradients（只用于 App 标记和进度条）
    public static var brandGradient: LinearGradient {
        LinearGradient(
            colors: [settings.accent.palette.brandTop, settings.accent.palette.brandBottom],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    /// App 图标的底色：比品牌按钮更深，保证纸白页在 Dock 和顶栏都跳出来。
    public static var appIconGradient: LinearGradient {
        LinearGradient(
            colors: [settings.accent.palette.iconTop, settings.accent.palette.iconBottom],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    /// 进度条：品牌色 → 深青，横向极窄渐变，像一条校样标记。
    public static var progressGradient: LinearGradient {
        LinearGradient(
            colors: [settings.accent.palette.brandTop, accentBlue, accentCyan],
            startPoint: .leading,
            endPoint: .trailing
        )
    }

    /// 画布：底色从上到下轻微收深，用来“承托”白卡而不是着色。
    public static var canvasGradient: LinearGradient {
        LinearGradient(
            colors: [canvasTop, canvas, canvasBottom],
            startPoint: .top,
            endPoint: .bottom
        )
    }

    /// 主按钮：同一色相内的极窄渐变，保留体积感但不花。
    public static var primaryGradient: LinearGradient {
        LinearGradient(
            colors: [settings.accent.palette.brandTop, settings.accent.palette.brandBottom],
            startPoint: .top,
            endPoint: .bottom
        )
    }

    /// Hero 卡片的纸面渐变：白 → 纸面，保留一点材质感。
    public static var heroGradient: LinearGradient {
        LinearGradient(
            colors: [Color.white, canvasTop, cardHover],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    /// 分隔线渐变：品牌色 → 次色 → 淡墨，只在发丝级别出现。
    public static var hairlineGradient: LinearGradient {
        LinearGradient(
            colors: [
                accentBlue.opacity(0.20),
                accentCyan.opacity(0.10),
                textPrimary.opacity(0.06)
            ],
            startPoint: .leading,
            endPoint: .trailing
        )
    }

    // MARK: - Text
    public static let textPrimary = Color(red: 0.114, green: 0.149, blue: 0.188)   // #1D2630
    public static let textSecondary = Color(red: 0.349, green: 0.392, blue: 0.439) // #596470
    public static let textMuted = Color(red: 0.384, green: 0.424, blue: 0.471)     // #626C78（≥4.5:1）

    // MARK: - Hairlines & Shadow
    public static let border = textPrimary.opacity(0.10)
    public static let borderHover = textPrimary.opacity(0.18)
    public static var borderStrong: Color { accentBlue.opacity(0.42) }
    public static let shadowColor = textPrimary.opacity(0.075)
    public static let shadowStrong = textPrimary.opacity(0.13)

    // MARK: - Geometry（连续圆角，嵌套时内圆角 = 外圆角 − 内边距）
    public static let radiusHero: CGFloat = 22
    public static let radiusCard: CGFloat = 16
    public static let radiusButton: CGFloat = 10
    public static let radiusBadge: CGFloat = 6
}

// MARK: - Button Styles

/// Apple 营销页式胶囊按钮：主操作为实心品牌蓝，次操作为白底发丝描边。
public struct LightButtonModifier: ViewModifier {
    var isProminent: Bool = false
    var isSelected: Bool = false
    @State private var isHovered = false

    public func body(content: Content) -> some View {
        content
            .font(.system(size: 12.5, weight: isProminent ? .semibold : .medium))
            .foregroundStyle(foregroundColor)
            .padding(.horizontal, isProminent ? 16 : 14)
            .padding(.vertical, 7.5)
            .background { backgroundShape }
            .overlay(
                Capsule().stroke(strokeColor, lineWidth: 1)
            )
            .shadow(
                color: isProminent ? LightTheme.accentBlue.opacity(isHovered ? 0.28 : 0.20) : LightTheme.shadowColor,
                radius: isProminent ? (isHovered ? 9 : 6) : 3,
                x: 0,
                y: isProminent ? 3 : 1
            )
            .contentShape(Capsule())
            .scaleEffect(isHovered ? 1.015 : 1.0)
            .onHover { hovering in
                withAnimation(.smooth(duration: 0.22)) {
                    isHovered = hovering
                }
            }
            .animation(.smooth(duration: 0.25), value: isSelected)
    }

    private var foregroundColor: Color {
        if isProminent { return .white }
        if isSelected { return LightTheme.accentBlue }
        return LightTheme.textPrimary
    }

    @ViewBuilder
    private var backgroundShape: some View {
        if isProminent {
            Capsule()
                .fill(LightTheme.primaryGradient)
                .overlay(
                    Capsule().fill(Color.white.opacity(isHovered ? 0.10 : 0))
                )
        } else if isSelected {
            Capsule().fill(LightTheme.accentBlue.opacity(0.10))
        } else {
            Capsule().fill(isHovered ? LightTheme.cardHover : Color.white)
        }
    }

    private var strokeColor: Color {
        if isProminent { return Color.white.opacity(0.16) }
        if isSelected { return LightTheme.accentBlue.opacity(0.28) }
        return isHovered ? LightTheme.borderHover : LightTheme.border
    }
}

public extension View {
    func lightButton(isProminent: Bool = false, isSelected: Bool = false) -> some View {
        modifier(LightButtonModifier(isProminent: isProminent, isSelected: isSelected))
    }
}

/// 与 AppIcon 同源的品牌标记：深墨蓝圆角底、轻斜折角纸页、页尾光标与解析火花。
/// 同一套矢量语言用于顶栏 26pt 与空状态 68pt，避免两处各画一个文档。
struct JParseMark: View {
    var size: CGFloat
    var showsShadow: Bool = true

    // 与 AppIcon 的纸页占卡片比例对齐（约 39% × 52%），小尺寸也不至于像空白章。
    private var pageWidth: CGFloat { size * 0.39 }
    private var pageHeight: CGFloat { size * 0.52 }
    private var foldWidth: CGFloat { pageWidth * 0.255 }
    private var lineHeight: CGFloat { max(0.55, size * 0.009) }
    private var lineGap: CGFloat { max(1.0, size * 0.033) }
    private var cursorSize: CGFloat { max(0.7, size * 0.017) }
    private var sparkSize: CGFloat { max(2.2, size * 0.09) }

    var body: some View {
        ZStack {
            tile
            page
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    private var tile: some View {
        RoundedRectangle(cornerRadius: size * 0.235, style: .continuous)
            .fill(LightTheme.appIconGradient)
            .overlay(
                RoundedRectangle(cornerRadius: size * 0.235, style: .continuous)
                    .fill(
                        RadialGradient(
                            colors: [Color.white.opacity(0.13), Color.clear],
                            center: .topLeading,
                            startRadius: 0,
                            endRadius: size * 0.78
                        )
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: size * 0.235, style: .continuous)
                    .stroke(Color.white.opacity(0.18), lineWidth: max(0.5, size * 0.012))
            )
            .shadow(
                color: showsShadow ? LightTheme.accentBlue.opacity(0.28) : .clear,
                radius: size * 0.14,
                y: size * 0.06
            )
    }

    private var page: some View {
        ZStack(alignment: .topLeading) {
            FoldedPageShape()
                .fill(Color(red: 0.988, green: 0.980, blue: 0.953))
                .frame(width: pageWidth, height: pageHeight)
                .shadow(
                    color: Color.black.opacity(0.24),
                    radius: max(0.6, size * 0.025),
                    y: max(0.6, size * 0.018)
                )

            FoldFlapShape()
                .fill(LightTheme.accentCyan)
                .frame(width: pageWidth, height: pageHeight)

            FoldFlapShape()
                .stroke(Color.white.opacity(0.22), lineWidth: max(0.4, size * 0.006))
                .frame(width: pageWidth, height: pageHeight)

            textLines
        }
        .frame(width: pageWidth, height: pageHeight)
        .overlay(alignment: .topTrailing) {
            FourPointSpark()
                .fill(Color(red: 0.608, green: 0.941, blue: 0.906))
                .frame(width: sparkSize, height: sparkSize)
                .shadow(color: LightTheme.accentCyan.opacity(0.45), radius: size * 0.02)
                .offset(x: sparkSize * 0.28, y: -sparkSize * 0.18)
        }
        .rotationEffect(.degrees(-8))
        .offset(x: -size * 0.012, y: -size * 0.014)
    }

    private var textLines: some View {
        let widths: [CGFloat] = size < 40 ? [0.60, 0.42] : [0.60, 0.46, 0.27]

        return VStack(alignment: .leading, spacing: lineGap) {
            ForEach(Array(widths.enumerated()), id: \.offset) { index, width in
                HStack(spacing: max(0.6, size * 0.008)) {
                    Capsule()
                        .fill(
                            index == widths.count - 1
                                ? Color(red: 0.345, green: 0.569, blue: 0.635)
                                : LightTheme.accentBlue
                        )
                        .frame(width: pageWidth * width, height: lineHeight)

                    if index == widths.count - 1 {
                        RoundedRectangle(cornerRadius: cursorSize * 0.24, style: .continuous)
                            .fill(LightTheme.accentCyan)
                            .frame(width: cursorSize, height: cursorSize * 0.88)
                    }
                }
            }
        }
        .offset(x: pageWidth * 0.17, y: pageHeight * 0.35)
        .accessibilityHidden(true)
    }
}

typealias LiteParseMark = JParseMark

private struct FoldedPageShape: Shape {
    func path(in rect: CGRect) -> Path {
        let radius = min(rect.width, rect.height) * 0.08
        let fold = rect.width * 0.255
        var path = Path()

        path.move(to: CGPoint(x: rect.minX + radius, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX - fold, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + fold))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - radius))
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX - radius, y: rect.maxY),
            control: CGPoint(x: rect.maxX, y: rect.maxY)
        )
        path.addLine(to: CGPoint(x: rect.minX + radius, y: rect.maxY))
        path.addQuadCurve(
            to: CGPoint(x: rect.minX, y: rect.maxY - radius),
            control: CGPoint(x: rect.minX, y: rect.maxY)
        )
        path.addLine(to: CGPoint(x: rect.minX, y: rect.minY + radius))
        path.addQuadCurve(
            to: CGPoint(x: rect.minX + radius, y: rect.minY),
            control: CGPoint(x: rect.minX, y: rect.minY)
        )
        path.closeSubpath()
        return path
    }
}

private struct FoldFlapShape: Shape {
    func path(in rect: CGRect) -> Path {
        let fold = rect.width * 0.255
        var path = Path()
        path.move(to: CGPoint(x: rect.maxX - fold, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + fold))
        path.addLine(to: CGPoint(x: rect.maxX - fold, y: rect.minY + fold))
        path.closeSubpath()
        return path
    }
}

private struct FourPointSpark: Shape {
    func path(in rect: CGRect) -> Path {
        let center = CGPoint(x: rect.midX, y: rect.midY)
        let outer = min(rect.width, rect.height) / 2
        let inner = outer * 0.24
        var path = Path()

        for index in 0..<8 {
            let angle = -CGFloat.pi / 2 + CGFloat(index) * .pi / 4
            let radius = index.isMultiple(of: 2) ? outer : inner
            let point = CGPoint(
                x: center.x + cos(angle) * radius,
                y: center.y + sin(angle) * radius
            )
            if index == 0 {
                path.move(to: point)
            } else {
                path.addLine(to: point)
            }
        }
        path.closeSubpath()
        return path
    }
}

/// 轻量按压反馈：按下略微收缩，松开弹回。
public struct PressableButtonStyle: ButtonStyle {
    var pressedScale: CGFloat
    var hoverScale: CGFloat

    public init(pressedScale: CGFloat = 0.97, hoverScale: CGFloat = 1.0) {
        self.pressedScale = pressedScale
        self.hoverScale = hoverScale
    }

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? pressedScale : hoverScale)
            .opacity(configuration.isPressed ? 0.85 : 1.0)
            .animation(.smooth(duration: 0.16), value: configuration.isPressed)
    }
}
