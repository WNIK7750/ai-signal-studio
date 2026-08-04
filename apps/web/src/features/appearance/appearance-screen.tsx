"use client";

import { IconCheck, IconMoon, IconPalette, IconSun } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusMark } from "@/components/status-mark";
import { clampToken, ThemeId, themePresets } from "@/lib/themes";

export function AppearanceScreen() {
  const [theme, setTheme] = useState<ThemeId>("signal-light");
  const [radius, setRadius] = useState(10);
  const [density, setDensity] = useState(12);
  const [fontSize, setFontSize] = useState(15);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const stored = localStorage.getItem("ai-signal-theme") as ThemeId | null;
      if (stored && themePresets.some((item) => item.id === stored)) {
        setTheme(stored);
      }
      setRadius(Number(localStorage.getItem("ai-signal-radius") ?? 10));
      setDensity(Number(localStorage.getItem("ai-signal-density") ?? 12));
      setFontSize(Number(localStorage.getItem("ai-signal-font-size") ?? 15));
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.setProperty("--radius", `${radius}px`);
    document.documentElement.style.setProperty("--density", `${density}px`);
    document.documentElement.style.setProperty("--base-font-size", `${fontSize}px`);
    localStorage.setItem("ai-signal-theme", theme);
    localStorage.setItem("ai-signal-radius", String(radius));
    localStorage.setItem("ai-signal-density", String(density));
    localStorage.setItem("ai-signal-font-size", String(fontSize));
  }, [density, fontSize, radius, theme]);

  return (
    <AppShell>
      <header className="topbar">
        <div>
          <span className="eyebrow">设置</span>
          <h1>外观</h1>
        </div>
        <span className="save-state">
          <IconCheck size={16} /> 自动保存在此浏览器
        </span>
      </header>
      <section className="settings-page">
        <div className="settings-heading">
          <span className="settings-icon"><IconPalette size={23} /></span>
          <div>
            <h2>选择主题</h2>
            <p>一键切换基础风格，再用设计令牌微调。</p>
          </div>
        </div>
        <div className="theme-grid">
          {themePresets.map((preset) => (
            <button
              key={preset.id}
              className={`theme-card ${theme === preset.id ? "selected" : ""}`}
              onClick={() => setTheme(preset.id)}
            >
              <span className="theme-preview" style={{ background: preset.colors[1] }}>
                <span style={{ background: preset.colors[0] }} />
                <i style={{ background: preset.colors[2] }} />
                <i style={{ background: preset.colors[2], opacity: .35 }} />
              </span>
              <span>
                <strong>{preset.name}</strong>
                <small>{preset.id === "midnight" ? <IconMoon size={14} /> : <IconSun size={14} />}</small>
              </span>
              {theme === preset.id && <IconCheck size={18} />}
            </button>
          ))}
        </div>

        <div className="token-layout">
          <section className="token-panel">
            <div className="section-heading"><h3>设计令牌</h3><span>实时</span></div>
            <TokenSlider
              label="圆角"
              value={radius}
              min={4}
              max={20}
              suffix="px"
              onChange={(value) => setRadius(clampToken(value, 4, 20))}
            />
            <TokenSlider
              label="间距"
              value={density}
              min={8}
              max={20}
              suffix="px"
              onChange={(value) => setDensity(clampToken(value, 8, 20))}
            />
            <TokenSlider
              label="字号"
              value={fontSize}
              min={13}
              max={18}
              suffix="px"
              onChange={(value) => setFontSize(clampToken(value, 13, 18))}
            />
            <label className="select-control">
              界面模式
              <select value={theme} onChange={(event) => setTheme(event.target.value as ThemeId)}>
                {themePresets.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}
              </select>
            </label>
          </section>
          <section className="live-preview">
            <span className="eyebrow">实时预览</span>
            <h3>AI 信息</h3>
            <article>
              <div><StatusMark priority="important" /><time>10:31</time></div>
              <strong>新的 Agent 工作流能力</strong>
              <p>摘要保持简短，让用户快速判断是否打开。</p>
            </article>
            <article>
              <div><StatusMark priority="watch" /><time>09:18</time></div>
              <strong>框架更新与工具动态</strong>
              <p>颜色、形状和文字标签共同表达状态。</p>
            </article>
          </section>
        </div>
      </section>
    </AppShell>
  );
}

function TokenSlider({
  label, value, min, max, suffix, onChange,
}: {
  label: string; value: number; min: number; max: number; suffix: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="token-slider">
      <span><strong>{label}</strong><output>{value}{suffix}</output></span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}
