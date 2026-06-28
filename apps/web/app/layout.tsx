import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Quant Agent Trading",
  description: "Operational dashboard for agentic quant trading workflows"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
