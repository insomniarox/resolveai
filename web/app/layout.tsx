import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "ResolveAI Incident Investigations",
  description: "Review synthetic incidents and their investigation evidence.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
