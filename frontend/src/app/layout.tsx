// src/app/layout.tsx
import "./globals.css";
import type { Metadata } from "next";
import { Analytics } from "@/components/analytics";

export const metadata: Metadata = {
  title: "DataLock",
  description: "Hero build recommendations powered by real match data.",
  icons: {
    icon: 'logo/logo_svg.svg'
  }
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Analytics />
        {children}
      </body>
    </html>
  );
}
