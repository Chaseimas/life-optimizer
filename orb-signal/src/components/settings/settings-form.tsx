"use client";

import { useState } from "react";

interface SettingsFormProps {
  initialSettings: Record<string, string>;
}

export function SettingsForm({ initialSettings }: SettingsFormProps) {
  const [settings, setSettings] = useState(initialSettings);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const update = (key: string, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const save = async () => {
    setSaving(true);
    await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    setSaving(false);
  };

  const testWebhook = async () => {
    setTestResult("Sending...");
    const url = settings.discord_webhook_url;
    if (!url) { setTestResult("No webhook URL set"); return; }
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "ORB Signal Dashboard — Webhook test" }),
      });
      setTestResult(res.ok ? "Sent" : `Error: ${res.status}`);
    } catch {
      setTestResult("Failed to send");
    }
  };

  return (
    <div className="space-y-8 max-w-2xl">
      <section>
        <h2 className="text-lg font-semibold mb-3">Alerts</h2>
        <div className="bg-bg-card border border-border rounded-lg p-4 space-y-3">
          <div>
            <label className="block text-sm text-text-secondary mb-1">Discord Webhook URL</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={settings.discord_webhook_url ?? ""}
                onChange={(e) => update("discord_webhook_url", e.target.value)}
                placeholder="https://discord.com/api/webhooks/..."
                className="flex-1 bg-bg-primary border border-border rounded px-3 py-2 text-sm text-text-primary"
              />
              <button
                onClick={testWebhook}
                className="px-3 py-2 bg-blue/20 text-blue rounded text-sm hover:bg-blue/30"
              >
                Test
              </button>
            </div>
            {testResult && <p className="text-xs mt-1 text-text-muted">{testResult}</p>}
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Filters</h2>
        <div className="bg-bg-card border border-border rounded-lg p-4 space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-text-secondary mb-1">Max Range/ATR %</label>
              <input
                type="number"
                value={settings.max_range_atr_pct ?? "75"}
                onChange={(e) => update("max_range_atr_pct", e.target.value)}
                className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm text-text-primary"
              />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1">Time Cutoff (ET)</label>
              <input
                type="text"
                value={settings.time_cutoff ?? "11:30"}
                onChange={(e) => update("time_cutoff", e.target.value)}
                className="w-full bg-bg-primary border border-border rounded px-3 py-2 text-sm text-text-primary"
              />
            </div>
          </div>
        </div>
      </section>

      <button
        onClick={save}
        disabled={saving}
        className="px-6 py-2 bg-blue text-white rounded-lg font-medium hover:bg-blue/80 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Save Settings"}
      </button>
    </div>
  );
}
