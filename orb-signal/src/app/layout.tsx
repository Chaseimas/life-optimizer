import type { Metadata } from "next";
import { Sidebar } from "@/components/layout/sidebar";
import { MobileNav } from "@/components/layout/mobile-nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "ORB Signal Dashboard",
  description: "Crypto Opening Range Breakout signal engine",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg-primary text-text-primary">
        <div className="flex">
          <Sidebar />
          <main className="flex-1 p-6 pb-20 md:pb-6 min-h-screen">
            {children}
          </main>
        </div>
        <MobileNav />
      </body>
    </html>
  );
}
