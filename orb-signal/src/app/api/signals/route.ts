import { NextResponse } from "next/server";
import { getSignalHistory, getPerformanceStats } from "@/lib/db/queries/signals";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limit = Number(searchParams.get("limit") ?? "100");
  const offset = Number(searchParams.get("offset") ?? "0");

  const signals = getSignalHistory(limit, offset);
  const stats = getPerformanceStats();

  return NextResponse.json({ signals, stats });
}
