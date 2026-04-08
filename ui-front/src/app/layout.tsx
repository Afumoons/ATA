import type { Metadata } from "next";
import { IBM_Plex_Mono, Instrument_Sans } from "next/font/google";
import { ThemeProvider } from "@/components/theme-provider";
import { DashboardFrame } from "@/components/dashboard-frame";
import "./globals.css";

const instrumentSans = Instrument_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Autonomous Trading AI — Operator UI v1",
  description: "Premium read-only operator dashboard for the v1 trading control surface.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="dark" className={`${instrumentSans.variable} ${plexMono.variable}`}>
      <body>
        <ThemeProvider>
          <DashboardFrame>{children}</DashboardFrame>
        </ThemeProvider>
      </body>
    </html>
  );
}
