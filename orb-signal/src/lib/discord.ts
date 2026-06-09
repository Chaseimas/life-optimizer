export async function sendDiscordMessage(content: string): Promise<void> {
  const webhookUrl = process.env.DISCORD_WEBHOOK_URL;
  if (!webhookUrl) {
    console.log("[discord] No webhook URL configured. Message:");
    console.log(content);
    return;
  }

  const res = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });

  if (!res.ok) {
    console.error(`[discord] Webhook failed ${res.status}: ${await res.text()}`);
  }
}
