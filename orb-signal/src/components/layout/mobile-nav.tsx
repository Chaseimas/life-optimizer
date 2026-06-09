"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, History, Settings } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Live", icon: Activity },
  { href: "/history", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function MobileNav() {
  const pathname = usePathname();

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-bg-secondary border-t border-border flex justify-around py-2 z-50">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`flex flex-col items-center gap-0.5 text-xs ${
              active ? "text-blue" : "text-text-muted"
            }`}
          >
            <Icon size={20} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
