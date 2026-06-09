import { NextResponse } from "next/server";
import { getRangesByDate } from "@/lib/db/queries/ranges";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const date = searchParams.get("date") ?? new Date().toISOString().split("T")[0];

  const ranges = getRangesByDate(date);
  return NextResponse.json({ ranges, date });
}
