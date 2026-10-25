import SwiftUI

public struct GlassBackgroundView: View {
    @State private var animateOrb1 = false
    @State private var animateOrb2 = false
    @State private var animateOrb3 = false

    public init() {}

    public var body: some View {
        ZStack {
            // Base deep dark canvas
            Color(red: 0.04, green: 0.06, blue: 0.09)
                .ignoresSafeArea()

            // Subtle ambient grid pattern or mesh
            LinearGradient(
                colors: [
                    Color(red: 0.06, green: 0.10, blue: 0.18),
                    Color(red: 0.03, green: 0.05, blue: 0.08)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            // Luminous Orb 1: Cyan/Blue glow in top-left
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            Color(red: 0.18, green: 0.45, blue: 0.95).opacity(0.28),
                            Color(red: 0.18, green: 0.45, blue: 0.95).opacity(0.0)
                        ],
                        center: .center,
                        startRadius: 10,
                        endRadius: 320
                    )
                )
                .frame(width: 600, height: 600)
                .offset(
                    x: animateOrb1 ? -160 : -220,
                    y: animateOrb1 ? -120 : -180
                )
                .blur(radius: 60)

            // Luminous Orb 2: Emerald/Teal glow in bottom-right
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            Color(red: 0.08, green: 0.72, blue: 0.55).opacity(0.22),
                            Color(red: 0.08, green: 0.72, blue: 0.55).opacity(0.0)
                        ],
                        center: .center,
                        startRadius: 10,
                        endRadius: 300
                    )
                )
                .frame(width: 550, height: 550)
                .offset(
                    x: animateOrb2 ? 220 : 160,
                    y: animateOrb2 ? 180 : 120
                )
                .blur(radius: 60)

            // Luminous Orb 3: Violet accent in center-right
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            Color(red: 0.55, green: 0.28, blue: 0.92).opacity(0.16),
                            Color(red: 0.55, green: 0.28, blue: 0.92).opacity(0.0)
                        ],
                        center: .center,
                        startRadius: 10,
                        endRadius: 260
                    )
                )
                .frame(width: 480, height: 480)
                .offset(
                    x: animateOrb3 ? 140 : 80,
                    y: animateOrb3 ? -100 : -50
                )
                .blur(radius: 70)
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 9.0).repeatForever(autoreverses: true)) {
                animateOrb1.toggle()
            }
            withAnimation(.easeInOut(duration: 12.0).repeatForever(autoreverses: true)) {
                animateOrb2.toggle()
            }
            withAnimation(.easeInOut(duration: 15.0).repeatForever(autoreverses: true)) {
                animateOrb3.toggle()
            }
        }
    }
}
