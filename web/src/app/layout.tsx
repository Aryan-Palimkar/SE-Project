import type { Metadata } from "next"
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google"
import "./globals.css"

const sans = Inter({ variable: "--font-sans", subsets: ["latin"] })
const serif = Source_Serif_4({ variable: "--font-serif", subsets: ["latin"] })
const mono = JetBrains_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })

export const metadata: Metadata = {
  title: "SDLC Advisor",
  description: "Requirements engineering and SDLC selection grounded in the project brief and Indian regulations.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${sans.variable} ${serif.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full">{children}</body>
    </html>
  )
}
