import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ORB Signal Dashboard",
  description: "Crypto Opening Range Breakout signal engine",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg-primary text-text-primary">
        {children}
      </body>
    </html>
  );
}
