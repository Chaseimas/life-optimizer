import { SettingsForm } from "@/components/settings/settings-form";
import { getAllSettings } from "@/lib/db/queries/settings";

export const dynamic = "force-dynamic";

export default function SettingsPage() {
  const settings = getAllSettings();

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Settings</h1>
      <SettingsForm initialSettings={settings} />
    </div>
  );
}
