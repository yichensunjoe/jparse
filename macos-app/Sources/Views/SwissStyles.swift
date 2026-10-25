import SwiftUI

public enum SwissTheme {
    public static let canvasBg = Color(red: 0.05, green: 0.07, blue: 0.10)
    public static let sidebarBg = Color(red: 0.07, green: 0.09, blue: 0.13)
    public static let surfaceBg = Color(red: 0.09, green: 0.12, blue: 0.17)
    public static let surfaceHover = Color(red: 0.12, green: 0.15, blue: 0.22)

    public static let accentCobalt = Color(red: 0.22, green: 0.55, blue: 0.98)
    public static let accentAmber = Color(red: 0.92, green: 0.60, blue: 0.18)
    public static let accentEmerald = Color(red: 0.16, green: 0.76, blue: 0.48)
    public static let accentCrimson = Color(red: 0.94, green: 0.27, blue: 0.30)

    public static let textPrimary = Color(red: 0.94, green: 0.96, blue: 0.98)
    public static let textSecondary = Color(red: 0.55, green: 0.59, blue: 0.65)
    public static let textMuted = Color(red: 0.38, green: 0.42, blue: 0.48)

    public static let hairline = Color.white.opacity(0.09)
    public static let hairlineStrong = Color.white.opacity(0.18)
}

public struct SwissButtonModifier: ViewModifier {
    var isProminent: Bool = false
    var isSelected: Bool = false

    private var bgColor: Color {
        if isProminent {
            return SwissTheme.accentCobalt
        } else if isSelected {
            return SwissTheme.accentCobalt.opacity(0.12)
        } else {
            return SwissTheme.surfaceBg.opacity(0.60)
        }
    }

    private var borderColor: Color {
        if isProminent {
            return SwissTheme.accentCobalt
        } else if isSelected {
            return SwissTheme.accentCobalt.opacity(0.40)
        } else {
            return SwissTheme.hairline
        }
    }

    public func body(content: Content) -> some View {
        content
            .font(.system(size: 12, weight: isSelected || isProminent ? .semibold : .regular))
            .foregroundStyle(isProminent ? .white : (isSelected ? SwissTheme.accentCobalt : SwissTheme.textPrimary))
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(bgColor, in: RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(borderColor, lineWidth: 1.0)
            )
    }
}

public extension View {
    func swissButton(isProminent: Bool = false, isSelected: Bool = false) -> some View {
        modifier(SwissButtonModifier(isProminent: isProminent, isSelected: isSelected))
    }
}
