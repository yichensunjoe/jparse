import SwiftUI

public enum LightTheme {
    // Canvas & Backgrounds
    public static let canvasBg = Color(red: 0.965, green: 0.973, blue: 0.984) // #f6f8fb
    public static let cardBg = Color(red: 0.984, green: 0.988, blue: 1.0)     // #fbfcff 微蓝冷调
    public static let cardHover = Color(red: 0.976, green: 0.984, blue: 0.996)
    public static let controlBg = Color(red: 0.925, green: 0.937, blue: 0.953) // #eceff4
    public static let pillActiveBg = Color.white

    // Accents
    public static let accentBlue = Color(red: 0.14, green: 0.42, blue: 0.96) // #256be6
    public static let accentGreen = Color(red: 0.06, green: 0.65, blue: 0.45) // #10b981
    public static let accentAmber = Color(red: 0.88, green: 0.54, blue: 0.12) // #e08a1e
    public static let accentRed = Color(red: 0.92, green: 0.28, blue: 0.28)

    // Typography
    public static let textPrimary = Color(red: 0.09, green: 0.12, blue: 0.17) // #171f2c
    public static let textSecondary = Color(red: 0.40, green: 0.46, blue: 0.54) // #66758a
    public static let textMuted = Color(red: 0.60, green: 0.66, blue: 0.74) // #99a8bd

    // Borders & Hairlines
    public static let border = Color.black.opacity(0.06)
    public static let borderHover = Color.black.opacity(0.12)
    public static let borderStrong = Color.black.opacity(0.18)
    public static let shadowColor = Color.black.opacity(0.04)

    // Unified Corner Radii (三级梯度)
    public static let radiusCard: CGFloat = 10
    public static let radiusButton: CGFloat = 8
    public static let radiusBadge: CGFloat = 6
}

public struct LightButtonModifier: ViewModifier {
    var isProminent: Bool = false
    var isSelected: Bool = false

    private var fgColor: Color {
        if isProminent {
            return .white
        } else if isSelected {
            return LightTheme.accentBlue
        } else {
            return LightTheme.textPrimary
        }
    }

    private var bgColor: Color {
        if isProminent {
            return LightTheme.accentBlue
        } else if isSelected {
            return LightTheme.accentBlue.opacity(0.08)
        } else {
            return Color.white
        }
    }

    private var strokeColor: Color {
        if isProminent {
            return LightTheme.accentBlue
        } else if isSelected {
            return LightTheme.accentBlue.opacity(0.3)
        } else {
            return LightTheme.border
        }
    }

    public func body(content: Content) -> some View {
        content
            .font(.system(size: 12, weight: isSelected || isProminent ? .semibold : .medium))
            .foregroundStyle(fgColor)
            .padding(.horizontal, 13)
            .padding(.vertical, 7)
            .background(bgColor, in: RoundedRectangle(cornerRadius: LightTheme.radiusButton))
            .overlay(
                RoundedRectangle(cornerRadius: LightTheme.radiusButton)
                    .stroke(strokeColor, lineWidth: 1.0)
            )
            .shadow(color: isProminent ? LightTheme.accentBlue.opacity(0.18) : LightTheme.shadowColor, radius: 3, x: 0, y: 1)
    }
}

public extension View {
    func lightButton(isProminent: Bool = false, isSelected: Bool = false) -> some View {
        modifier(LightButtonModifier(isProminent: isProminent, isSelected: isSelected))
    }
}
