import { NextResponse } from "next/server";
import { loadDashboardData } from "../../../lib/dashboard-data.js";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const data = await loadDashboardData();
    return NextResponse.json({ ok: true, data });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Failed to load dashboard data" },
      { status: 500 },
    );
  }
}

