"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, History, Settings } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Live View", icon: Activity },
  { href: "/history", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex flex-col w-56 bg-bg-secondary border-r border-border min-h-screen p-4">
      <div className="mb-8">
        <h1 className="text-lg font-bold text-text-primary">ORB Signal</h1>
        <p className="text-xs text-text-muted">Crypto Breakout Engine</p>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-blue/10 text-blue"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-card"
              }`}
            >
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
