import { NextResponse } from "next/server";
import { getAllSettings, setSetting } from "@/lib/db/queries/settings";

export async function GET() {
  return NextResponse.json(getAllSettings());
}

export async function PUT(request: Request) {
  const body = await request.json();
  for (const [key, value] of Object.entries(body)) {
    setSetting(key, JSON.stringify(value));
  }
  return NextResponse.json({ ok: true });
}
