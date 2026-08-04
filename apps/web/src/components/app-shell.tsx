"use client";

import {
  IconAdjustments,
  IconRobot,
  IconChevronLeft,
  IconChevronRight,
  IconDatabase,
  IconCards,
  IconChecklist,
  IconHistory,
  IconLayoutSidebarLeftCollapse,
  IconPalette,
  IconRadar2,
  IconSparkles,
} from "@tabler/icons-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const primary = [
  { href: "/timeline", label: "AI 信息", icon: IconRadar2 },
  { href: "/review", label: "审核", icon: IconChecklist },
  { href: "/cards", label: "卡片", icon: IconCards },
  { href: "/agent", label: "对话 Agent", icon: IconRobot },
  { href: "/runs", label: "运行记录", icon: IconHistory },
];
const settings = [
  { href: "/settings/sources", label: "来源", icon: IconDatabase },
  { href: "/settings/appearance", label: "外观", icon: IconPalette },
];

export function AppShell({
  children,
  aside,
  asideOpen = false,
  onAsideToggle,
}: {
  children: React.ReactNode;
  aside?: React.ReactNode;
  asideOpen?: boolean;
  onAsideToggle?: () => void;
}) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      setCollapsed(localStorage.getItem("ai-signal-nav-collapsed") === "1");
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  function toggleNavigation() {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem("ai-signal-nav-collapsed", next ? "1" : "0");
      return next;
    });
  }

  return (
    <div
      className={`app-shell ${collapsed ? "nav-collapsed" : ""} ${
        asideOpen ? "aside-open" : ""
      }`}
    >
      <aside className="side-nav" aria-label="主导航">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <IconSparkles size={21} stroke={1.8} />
          </span>
          <strong>AI Signal Studio</strong>
        </div>
        <nav className="nav-list">
          {primary.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={pathname === href ? "active" : ""}
              title={collapsed ? label : undefined}
            >
              <Icon size={21} stroke={1.7} />
              <span>{label}</span>
            </Link>
          ))}
          <p className="nav-section-label">设置</p>
          {settings.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={pathname === href ? "active" : ""}
              title={collapsed ? label : undefined}
            >
              <Icon size={21} stroke={1.7} />
              <span>{label}</span>
            </Link>
          ))}
        </nav>
        <button
          className="nav-collapse"
          onClick={toggleNavigation}
          aria-label={collapsed ? "展开左侧导航" : "收起左侧导航"}
          title={collapsed ? "展开" : "收起"}
        >
          {collapsed ? (
            <IconChevronRight size={19} />
          ) : (
            <>
              <IconLayoutSidebarLeftCollapse size={19} />
              <span>收起</span>
            </>
          )}
        </button>
      </aside>
      <main className="workspace">{children}</main>
      {aside && asideOpen && (
        <aside className="right-aside" aria-label="辅助面板">
          {aside}
        </aside>
      )}
      {aside && onAsideToggle && (
        <button
          className={`aside-handle ${asideOpen ? "is-open" : ""}`}
          onClick={onAsideToggle}
          aria-label={asideOpen ? "收起右侧面板" : "展开右侧面板"}
          title={asideOpen ? "收起右侧面板" : "展开右侧面板"}
        >
          {asideOpen ? (
            <IconChevronLeft size={18} />
          ) : (
            <IconAdjustments size={18} />
          )}
        </button>
      )}
    </div>
  );
}
